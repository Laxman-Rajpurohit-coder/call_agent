import uuid
import asyncio
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.orm import Session
from services.dashboard.app.database import get_db
from services.dashboard.app.models import CallSession, CallInteraction, Contact, Campaign, CampaignContact, Organization
from services.dashboard.app.schemas import CallSessionResponse

router = APIRouter(prefix="/calls", tags=["Calls"])

class ManualDialRequest(BaseModel):
    phone_number: str
    contact_name: Optional[str] = None
    voice_model: Optional[str] = "cartesia_hi_sonic"
    script_content: Optional[str] = None
    call_mode: Optional[str] = "AUTO"
    system_prompt: Optional[str] = None
    dial_mode: Optional[str] = "app"  # app (Wi-Fi/SIP) vs sim (Cellular GSM)

@router.get("", response_model=List[CallSessionResponse])
async def list_calls(
    status: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    query = db.query(CallSession)
    if status:
        query = query.filter(CallSession.status == status)
    sessions = query.order_by(CallSession.created_at.desc()).limit(limit).all()
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
    return session

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


