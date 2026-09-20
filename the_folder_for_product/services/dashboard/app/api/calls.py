import uuid
import asyncio
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from services.dashboard.app.database import get_db
from services.dashboard.app.models import CallSession, CallInteraction, Contact, Campaign, CampaignContact, Organization
from services.dashboard.app.schemas import CallSessionResponse
from services.dashboard.app.dependencies import get_authorized_call, get_current_user
from services.dashboard.app.services.storage import storage_service

router = APIRouter(prefix="/calls", tags=["Calls"])

class ManualDialRequest(BaseModel):
    phone_number: str
    contact_name: Optional[str] = None
    voice_model: Optional[str] = "cartesia_hi_sonic"
    script_content: Optional[str] = None
    call_mode: Optional[str] = "AUTO"
    system_prompt: Optional[str] = None
    dial_mode: Optional[str] = "app"  # app (Wi-Fi/SIP) vs sim (Cellular GSM)

from datetime import datetime, timedelta
from services.dashboard.app.services.call_registry import call_registry
from services.dashboard.app.services.call_reconciler import reconcile_active_sessions

def enrich_call_session(call: CallSession):
    """Enriches CallSession with handler attribution, media status, and live timing."""
    h_type = "AI"
    h_id = None
    h_name = "Superfone AI Ananya"
    h_role = "AI Voice Receptionist"
    
    if call.handled_by_user_id and getattr(call, 'handled_by', None):
        h_type = "HUMAN"
        h_id = call.handled_by.id
        h_name = getattr(call.handled_by, 'name', "Human Agent")
        h_role = getattr(call.handled_by, "role", "Agent")
    elif getattr(call, 'handoff_status', None) in ("WAITING_FOR_AGENT", "AGENT_ACCEPTED", "BRIDGING"):
        h_type = "TRANSFERRING"
        h_name = "Ringing Human Agents..."
        h_role = "Handoff in Progress"
    
    call.handler = {
        "type": h_type,
        "id": h_id,
        "name": h_name,
        "role": h_role
    }
    
    is_live = call.status in ("in_progress", "active", "connected", "initiated", "RINGING", "CONNECTED", "HUMAN_CONNECTED", "RECOVERY_PENDING")
    media_stat = getattr(call, "media_status", None) or ("RECEIVING" if is_live else "DISCONNECTED")
    last_pkt = call.last_heartbeat_at.isoformat() if getattr(call, "last_heartbeat_at", None) else (call.updated_at.isoformat() if call.updated_at else None)

    call.media = {
        "rtp": media_stat,
        "codec": "G.711 PCMU",
        "sample_rate": 8000,
        "last_packet_at": last_pkt
    }
    call.vad_state = getattr(call, "vad_state", None) or ("LISTENING" if is_live else "IDLE")
    call.handled_by_name = h_name if h_type == "HUMAN" else None
    call.agent_name = h_name if h_type == "AI" else "Superfone AI"
    call.connected_at = call.started_at
    return call

async def reconcile_stale_calls(db: Session, max_age_seconds: int = 180):
    """Heartbeat-based safe reconciler (Constraint 2)."""
    return await reconcile_active_sessions(db, heartbeat_timeout_seconds=20, recovery_timeout_seconds=25)

@router.get("/active", response_model=List[CallSessionResponse])
async def list_active_calls(db: Session = Depends(get_db)):
    """Returns only authoritative currently active live calls (heartbeat-verified)."""
    await reconcile_active_sessions(db, heartbeat_timeout_seconds=20, recovery_timeout_seconds=25)
    active_sessions = db.query(CallSession).filter(
        CallSession.status.in_(["in_progress", "active", "connected", "initiated", "RINGING", "CONNECTED", "HUMAN_CONNECTED", "RECOVERY_PENDING"])
    ).order_by(CallSession.created_at.desc()).all()
    for s in active_sessions:
        enrich_call_session(s)
    return active_sessions

@router.post("/cleanup-stale")
async def cleanup_stale_endpoint(db: Session = Depends(get_db)):
    """Explicitly reconciles and purges all dead/stale in_progress calls."""
    count = await reconcile_active_sessions(db, heartbeat_timeout_seconds=10, recovery_timeout_seconds=15)
    return {"status": "ok", "cleaned_count": count}

@router.post("/{call_id}/hangup")
async def hangup_call_endpoint(call_id: str, db: Session = Depends(get_db)):
    """Terminates an active call session, sending SIP BYE and marking it completed."""
    from services.dashboard.app.services.event_bus import broadcast_call_event
    session = db.query(CallSession).filter(CallSession.id == call_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Call session not found")
    
    # 1. Terminate softphone session if active in-memory
    try:
        await call_registry.terminate_call(call_id)
        from microsip_direct_caller import terminate_call
        await terminate_call(call_id)
    except Exception as ex:
        print(f"[Hangup Warning] {ex}")
    
    # 2. Finalize DB session
    session.status = "completed"
    session.media_status = "DISCONNECTED"
    session.vad_state = "IDLE"
    session.ended_at = datetime.utcnow()
    if session.started_at:
        session.duration_s = max(round((session.ended_at - session.started_at).total_seconds(), 1), session.duration_s or 0.0)
    db.commit()
    
    # 3. Broadcast CALL_ENDED event with per-call sequence
    if broadcast_call_event:
        await broadcast_call_event("CALL_ENDED", call_id, {
            "reason": "OPERATOR_HANGUP",
            "duration_s": session.duration_s
        })
    return {"status": "terminated", "call_id": call_id, "duration_s": session.duration_s}

@router.get("", response_model=List[CallSessionResponse])
async def list_calls(
    status: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    await reconcile_stale_calls(db, max_age_seconds=180)
    query = db.query(CallSession)
    if status:
        query = query.filter(CallSession.status == status)
    sessions = query.order_by(CallSession.created_at.desc()).limit(limit).all()
    for s in sessions:
        enrich_call_session(s)
    return sessions

@router.get("/agent/{agent_id}")
async def list_calls_for_agent(agent_id: str, limit: int = 100, db: Session = Depends(get_db)):
    """
    Returns all calls associated with an agent:
    - Calls to contacts owned by this agent (lead_owner_id == agent_id)
    - Calls from campaigns assigned to this agent (Campaign.assigned_agent_id == agent_id)
    Includes recording_url, full transcript[], and intent_detected from CallInteraction.
    """
    from services.dashboard.app.models import Contact as ContactModel, Campaign as CampaignModel
    # Get contact IDs owned by this agent
    owned_contact_ids = [
        c.id for c in db.query(ContactModel).filter(ContactModel.lead_owner_id == agent_id).all()
    ]
    # Get campaign IDs assigned to this agent
    assigned_campaign_ids = [
        c.id for c in db.query(CampaignModel).filter(CampaignModel.assigned_agent_id == agent_id).all()
    ]

    all_calls = db.query(CallSession).order_by(CallSession.created_at.desc()).limit(limit).all()

    result = []
    for call in all_calls:
        in_owned = call.contact_id and call.contact_id in owned_contact_ids
        in_campaign = call.campaign_id and call.campaign_id in assigned_campaign_ids if hasattr(call, 'campaign_id') else False
        if not (in_owned or in_campaign or not owned_contact_ids):
            continue

        # Get intent from CallInteraction
        intent_detected = None
        ai_summary = None
        sentiment = None
        if call.interactions:
            last_interaction = call.interactions[-1]
            intent_detected = last_interaction.intent_detected
            ai_summary = last_interaction.ai_summary
            sentiment = getattr(last_interaction, 'sentiment', None)

        # Get contact details
        contact_name = None
        contact_phone = None
        if call.contact:
            contact_name = call.contact.name
            contact_phone = call.contact.phone_number
            cf = call.contact.custom_fields or {}
            if not intent_detected:
                intent_detected = cf.get("last_intent") or cf.get("bot_intent")
            if not ai_summary:
                ai_summary = cf.get("bot_summary")

        result.append({
            "id": call.id,
            "from_number": call.from_number,
            "to_number": call.to_number,
            "contact_id": call.contact_id,
            "contact_name": contact_name or call.from_number,
            "contact_phone": contact_phone or call.to_number,
            "direction": call.direction,
            "status": call.status,
            "duration_s": call.duration_s or 0,
            "recording_url": call.recording_url,
            "transcript": call.transcript or [],
            "intent_detected": intent_detected,
            "ai_summary": ai_summary,
            "sentiment": sentiment,
            "created_at": call.created_at.isoformat() if call.created_at else None,
            "started_at": call.started_at.isoformat() if call.started_at else None,
            "ended_at": call.ended_at.isoformat() if call.ended_at else None,
        })

    return result

@router.get("/audio/{wav_name}")
async def serve_call_audio(wav_name: str):
    """Serves recorded telephony audio WAV files for turn-by-turn live playback."""
    import os
    from fastapi.responses import FileResponse
    from pathlib import Path
    safe_name = os.path.basename(wav_name)
    workspace_dir = str(Path(__file__).resolve().parents[4])
    candidates = [
        os.path.join(workspace_dir, safe_name),
        os.path.join(workspace_dir, "recordings", safe_name),
        os.path.join(r"c:\daily_works\superfone_call", safe_name),
        os.path.join(r"c:\daily_works\superfone_call", "recordings", safe_name),
    ]
    file_path = next((p for p in candidates if os.path.exists(p)), None)
    if not file_path:
        raise HTTPException(status_code=404, detail="Audio file not found")
    return FileResponse(file_path, media_type="audio/wav")

@router.get("/{call_id}", response_model=CallSessionResponse)
async def get_call_detail(call_id: str, db: Session = Depends(get_db)):

    session = db.query(CallSession).filter(CallSession.id == call_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Call session not found")
    enrich_call_session(session)
    return session

@router.get("/{call_id}/recording")
async def stream_call_recording(
    call_id: str,
    call: CallSession = Depends(get_authorized_call)
):
    """
    Securely stream call audio recording.
    Enforces tenant isolation, intra-tenant agent confidentiality,
    and opaque path confinement.
    """
    key_candidate = call.recording_storage_key or call.recording_url or f"{call.id}.wav"
    try:
        file_path = storage_service.resolve_recording_path(key_candidate)
    except ValueError as ex:
        raise HTTPException(status_code=400, detail=str(ex))

    if not file_path:
        raise HTTPException(status_code=404, detail="Recording audio not found")

    return FileResponse(file_path, media_type="audio/wav")

@router.post("/manual-dial")
async def trigger_manual_dial(
    req: ManualDialRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Triggers an instant direct manual telephony call to a phone number.
    Auto-launches MicroSIP on desktop, creates/retrieves contact & call session,
    and streams the AI agent call session live!
    """
    phone = req.phone_number.strip()
    if not phone:
        raise HTTPException(status_code=400, detail="Phone number is required")

    # 1. Get or create Contact
    contact = db.query(Contact).filter(Contact.phone_number == phone).first()
    if not contact:
        org = db.query(Organization).first()
        contact = Contact(
            id=str(uuid.uuid4()),
            organization_id=org.id if org else str(uuid.uuid4()),
            phone_number=phone,
            name=req.contact_name or f"Manual Lead {phone}",
            status="ACTIVE",
            preferred_language="hi"
        )
        db.add(contact)
        db.commit()
        db.refresh(contact)

    # 2. Create ad-hoc campaign for manual call
    mode = req.call_mode if req.call_mode in ("INTERACTIVE_AI", "SCRIPT") else ("INTERACTIVE_AI" if not req.script_content else "SCRIPT")
    script = req.script_content.strip() if (mode == "SCRIPT" and req.script_content) else ""
    prompt = req.system_prompt.strip() if (mode == "INTERACTIVE_AI" and req.system_prompt) else ""
    voice = req.voice_model or "deepgram_aura_asteria"

    campaign = Campaign(
        name=f"Manual Call ({mode}): {contact.name or phone}",
        description=prompt if mode == "INTERACTIVE_AI" else script,
        type=mode,
        script_content=script if mode == "SCRIPT" else "",
        voice_model=voice,
        max_concurrency=1,
        status="RUNNING"
    )
    db.add(campaign)
    db.commit()
    db.refresh(campaign)

    cc = CampaignContact(campaign_id=campaign.id, contact_id=contact.id, status="IN_PROGRESS", attempt_count=1)
    db.add(cc)
    db.commit()

    # 3. Trigger MicroSIP caller session concurrently without 30s FastAPI background task queueing
    from microsip_direct_caller import run_microsip_session
    asyncio.create_task(run_microsip_session(campaign.id, script_content=script, voice_model=voice, call_mode=mode, system_prompt=prompt))

    return {
        "status": "dialing",
        "message": f"Manual call initiated to {phone}",
        "campaign_id": campaign.id,
        "contact_id": contact.id,
        "phone_number": phone
    }

@router.post("/{call_id}/auto-label")
async def auto_label_call_endpoint(call_id: str, db: Session = Depends(get_db)):
    """Triggers LLM transcript analysis & auto-labeling for a call session."""
    from services.dashboard.app.api.tools import tool_analyze_and_label, AnalyzeAndLabelInput
    return tool_analyze_and_label(AnalyzeAndLabelInput(call_id=call_id), db)

# ------------------------------------------------------------------------------
# HANDOFF & SUPERVISOR API ROUTES
# ------------------------------------------------------------------------------
class HandoffInitiateRequest(BaseModel):
    call_session_id: str
    reason: Optional[str] = "CUSTOMER_REQUESTED_HUMAN"
    ai_summary: Optional[str] = None
    idempotency_key: Optional[str] = None

class HandoffAcceptRequest(BaseModel):
    call_session_id: str
    agent_id: str
    idempotency_key: Optional[str] = None

class HandoffRejectRequest(BaseModel):
    call_session_id: str
    agent_id: str

class CustomerHangupRequest(BaseModel):
    call_session_id: str

class SupervisorActionRequest(BaseModel):
    call_session_id: str
    supervisor_id: str
    action: str # LISTEN, WHISPER, BARGE, STOP

@router.post("/handoff/initiate")
async def initiate_call_handoff(req: HandoffInitiateRequest, db: Session = Depends(get_db)):
    """Triggers parallel ringing handoff to available agent pool."""
    from services.dashboard.app.services.call_handoff_manager import CallHandoffManager
    res = CallHandoffManager.initiate_handoff(
        db,
        call_session_id=req.call_session_id,
        reason=req.reason or "CUSTOMER_REQUESTED_HUMAN",
        ai_summary=req.ai_summary,
        idempotency_key=req.idempotency_key
    )
    if "error" in res:
        raise HTTPException(status_code=400, detail=res["error"])
    return res

@router.post("/handoff/accept")
async def accept_call_handoff(req: HandoffAcceptRequest, db: Session = Depends(get_db)):
    """Atomically accepts call handoff for first answering agent."""
    from services.dashboard.app.services.call_handoff_manager import CallHandoffManager
    res = CallHandoffManager.atomic_accept_call(
        db,
        call_session_id=req.call_session_id,
        agent_id=req.agent_id,
        idempotency_key=req.idempotency_key
    )
    if res.get("status") == "already_accepted":
        raise HTTPException(status_code=409, detail=res)
    if "error" in res:
        raise HTTPException(status_code=400, detail=res["error"])
    return res

@router.post("/handoff/reject")
async def reject_call_handoff(req: HandoffRejectRequest, db: Session = Depends(get_db)):
    """Rejects handoff offer for a specific agent and releases agent to AVAILABLE."""
    from services.dashboard.app.services.call_handoff_manager import CallHandoffManager
    return CallHandoffManager.reject_call(db, req.call_session_id, req.agent_id)

@router.post("/handoff/customer-hangup")
async def customer_hangup_handoff(req: CustomerHangupRequest, db: Session = Depends(get_db)):
    """Cancels ringing legs and releases agents when customer hangs up."""
    from services.dashboard.app.services.call_handoff_manager import CallHandoffManager
    return CallHandoffManager.handle_customer_hangup(db, req.call_session_id)

@router.post("/supervisor/action")
async def supervisor_call_action(req: SupervisorActionRequest, db: Session = Depends(get_db)):
    """Triggers LISTEN, WHISPER, or BARGE supervisor action on an active call."""
    from services.dashboard.app.services.call_handoff_manager import CallHandoffManager
    res = CallHandoffManager.supervisor_action(db, req.call_session_id, req.supervisor_id, req.action.upper())
    if "error" in res:
        raise HTTPException(status_code=400, detail=res["error"])
    return res

@router.get("/{call_id}/handoff-attempts")
async def get_call_handoff_attempts(call_id: str, db: Session = Depends(get_db)):
    """Returns history of all offered agent ringing legs for a call session."""
    from services.dashboard.app.models.crm import CallHandoffAttempt
    attempts = db.query(CallHandoffAttempt).filter(CallHandoffAttempt.call_session_id == call_id).all()
    return [{
        "id": a.id,
        "agent_id": a.agent_id,
        "offered_at": a.offered_at.isoformat() if a.offered_at else None,
        "answered_at": a.answered_at.isoformat() if a.answered_at else None,
        "rejected_at": a.rejected_at.isoformat() if a.rejected_at else None,
        "cancelled_at": a.cancelled_at.isoformat() if a.cancelled_at else None,
        "result": a.result
    } for a in attempts]


