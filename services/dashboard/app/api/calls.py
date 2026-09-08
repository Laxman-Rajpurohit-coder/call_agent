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

@router.get("/audio/{wav_name}")
async def serve_call_audio(wav_name: str):
    """Serves recorded telephony audio WAV files for turn-by-turn live playback."""
    import os
    from fastapi.responses import FileResponse
    safe_name = os.path.basename(wav_name)
    file_path = os.path.join(r"c:\daily_works\superfone_call", safe_name)
    if not os.path.exists(file_path):
        artifact_path = os.path.join(r"C:\Users\msanj\.gemini\antigravity\brain\8fd7d2de-313c-4386-802f-400cc03a7507", safe_name)
        if os.path.exists(artifact_path):
            file_path = artifact_path
        else:
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


