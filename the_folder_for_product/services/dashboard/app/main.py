import os
import sys
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path

WORKSPACE_DIR = str(Path(__file__).resolve().parents[3])
LEGACY_DIR = r"c:\daily_works\superfone_call"

for d in (WORKSPACE_DIR, LEGACY_DIR):
    if os.path.exists(d) and d not in sys.path:
        sys.path.insert(0, d)

ROOT_DIR = WORKSPACE_DIR if os.path.exists(WORKSPACE_DIR) else LEGACY_DIR

from services.dashboard.app.config import settings
from services.dashboard.app.database import engine, Base, run_migrations
from services.dashboard.app.api import api_router
from services.dashboard.app.services.event_bus import log_tailer_task

async def reminder_checker_task():
    from datetime import datetime
    from services.dashboard.app.database import SessionLocal
    from services.dashboard.app.models.crm import LeadReminder, Contact
    from services.dashboard.app.services.event_bus import manager
    
    while True:
        try:
            await asyncio.sleep(5)
            db = SessionLocal()
            now = datetime.utcnow()
            due_reminders = db.query(LeadReminder).filter(
                LeadReminder.is_triggered == False,
                LeadReminder.remind_at <= now
            ).all()

            for rem in due_reminders:
                rem.is_triggered = True
                contact = db.query(Contact).filter(Contact.id == rem.contact_id).first() if rem.contact_id else None
                alert_payload = {
                    "type": "REMINDER_ALERT",
                    "reminder_id": rem.id,
                    "note": rem.note,
                    "contact_name": contact.name if contact else "Lead",
                    "contact_phone": contact.phone_number if contact else "",
                    "remind_at": rem.remind_at.isoformat()
                }
                await manager.broadcast(alert_payload)
            
            if due_reminders:
                db.commit()
            db.close()
        except Exception as ex:
            await asyncio.sleep(5)

async def stale_reaper_task():
    from services.dashboard.app.database import SessionLocal
    from services.dashboard.app.api.calls import reconcile_stale_calls
    while True:
        try:
            await asyncio.sleep(30)
            db = SessionLocal()
            await reconcile_stale_calls(db, max_age_seconds=180)
            db.close()
        except Exception:
            await asyncio.sleep(30)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Validate critical production secrets
    from services.dashboard.app.config import validate_production_secrets
    validate_production_secrets()

    # Initialize DB tables & migrations
    from services.dashboard.app.models.crm import IncomingCallConfig, IncomingCallConfigAudit
    Base.metadata.create_all(bind=engine)
    run_migrations()
    
    # Run immediate stale call cleanup on startup
    try:
        from services.dashboard.app.database import SessionLocal
        from services.dashboard.app.api.calls import reconcile_stale_calls
        init_db = SessionLocal()
        cleaned = await reconcile_stale_calls(init_db, max_age_seconds=60)
        init_db.close()
        if cleaned:
            print(f"🧹 [Startup Reaper] Reconciled {cleaned} orphaned call sessions to COMPLETED.")
    except Exception as ex:
        print(f"[Startup Reaper Warning] {ex}")
    
    # Start background log tailer, reminder checker, and stale reaper tasks
    tailer_task = asyncio.create_task(log_tailer_task())
    reminder_task = asyncio.create_task(reminder_checker_task())
    reaper_task = asyncio.create_task(stale_reaper_task())

    # Finish post-call analyses that a restart/crash interrupted (PENDING / FAILED / stale RUNNING)
    async def _retry_analyses_on_startup():
        await asyncio.sleep(10)  # let the server finish starting first
        try:
            from services.dashboard.app.services.call_analysis import retry_pending_analyses
            await retry_pending_analyses()
        except Exception as ex:
            print(f"[Call Analysis Retry Warning] {ex}")
    analysis_retry_task = asyncio.create_task(_retry_analyses_on_startup())
    yield
    tailer_task.cancel()
    reminder_task.cancel()
    reaper_task.cancel()
    analysis_retry_task.cancel()

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API V1 Router
app.include_router(api_router, prefix=settings.API_V1_STR)

# Root WebSocket for Live Call Events & Real-Time Logs
from services.dashboard.app.services.event_bus import manager
from fastapi import WebSocket, WebSocketDisconnect

@app.websocket("/ws/live")
@app.websocket("/ws/telephony/monitor")
async def root_ws_live(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

# Serve Call Recordings Static Directory
RECORDINGS_DIR = os.path.join(ROOT_DIR, "recordings")
os.makedirs(RECORDINGS_DIR, exist_ok=True)
app.mount("/recordings", StaticFiles(directory=RECORDINGS_DIR), name="recordings")

# Direct Exotel Outbound Call Telephony Endpoint
from pydantic import BaseModel
from typing import Optional
import base64
import httpx
import uuid

class ExotelOutboundRequest(BaseModel):
    to: str
    contact_name: Optional[str] = None
    script_content: Optional[str] = ""
    system_prompt: Optional[str] = ""
    provider: Optional[str] = "vobiz"
    call_mode: Optional[str] = "INTERACTIVE_AI"
    voice_model: Optional[str] = "cartesia_hi_sonic"
    dial_mode: Optional[str] = "sim"

@app.post("/api/telephony/outbound-call")
@app.post("/api/v1/telephony/outbound-call")
async def handle_telephony_outbound_call(req: ExotelOutboundRequest):
    """
    Triggers automated outbound cellular/PSTN call via Vobiz or Exotel API.
    """
    to_phone = req.to.strip() if req.to else ""
    if not to_phone:
        raise HTTPException(status_code=400, detail="Recipient phone number (to) is required.")

    # 1. Primary Outbound Provider: VOBIZ API
    vobiz_auth_id = os.environ.get("VOBIZ_AUTH_ID")
    vobiz_token = os.environ.get("VOBIZ_AUTH_TOKEN")
    vobiz_caller_id = os.environ.get("VOBIZ_CALLER_ID", "918064269009")
    vobiz_public_url = os.environ.get("VOBIZ_PUBLIC_URL", "https://drool-envoy-sandy.ngrok-free.dev")

    digits_only = "".join(c for c in to_phone if c.isdigit())
    if len(digits_only) == 10:
        clean_vobiz_to = "91" + digits_only
    elif digits_only.startswith("91") and len(digits_only) == 12:
        clean_vobiz_to = digits_only
    else:
        clean_vobiz_to = digits_only

    if vobiz_auth_id and vobiz_token and (req.provider == "vobiz" or not os.environ.get("EXOTEL_API_KEY")):
        call_uuid = str(uuid.uuid4())
        vobiz_url = f"https://api.vobiz.ai/api/v1/Account/{vobiz_auth_id}/Call/"
        answer_url = f"{vobiz_public_url.rstrip('/')}/answer?cid={call_uuid}"

        # Record call session and custom fields in CRM DB before placing call
        from services.dashboard.app.database import SessionLocal
        from services.dashboard.app.models import CallSession, Organization, Contact
        with SessionLocal() as db_s:
            org = db_s.query(Organization).first()
            org_id = org.id if org else str(uuid.uuid4())
            contact = db_s.query(Contact).filter(Contact.phone_number == to_phone).first()
            if not contact:
                contact = Contact(
                    id=str(uuid.uuid4()),
                    organization_id=org_id,
                    phone_number=to_phone,
                    name=req.contact_name or f"Lead {to_phone}",
                    status="ACTIVE",
                    preferred_language="hi"
                )
                db_s.add(contact)
                db_s.commit()
                db_s.refresh(contact)

            custom_data = {
                "call_mode": req.call_mode or ("SCRIPT" if req.script_content else "INTERACTIVE_AI"),
                "voice_model": req.voice_model or "cartesia_hi_sonic",
                "script_content": req.script_content.strip() if req.script_content else "",
                "system_prompt": req.system_prompt.strip() if req.system_prompt else "",
                "contact_name": req.contact_name or ""
            }
            session_rec = CallSession(
                id=call_uuid,
                organization_id=org_id,
                contact_id=contact.id if contact else None,
                provider="vobiz",
                direction="outbound",
                dial_mode=req.dial_mode or "sim",
                from_number=vobiz_caller_id,
                to_number=to_phone,
                status="in_progress",
                duration_s=0.0,
                custom_fields=custom_data
            )
            db_s.add(session_rec)
            db_s.commit()

        headers = {
            "X-Auth-ID": vobiz_auth_id,
            "X-Auth-Token": vobiz_token,
            "Content-Type": "application/json"
        }
        body = {
            "from": vobiz_caller_id,
            "to": clean_vobiz_to,
            "answer_url": answer_url,
            "answer_method": "POST"
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(vobiz_url, headers=headers, json=body)

            data = resp.json() if resp.status_code in (200, 201) else {"error": resp.text}
            print(f"[Vobiz Outbound Call] Dialed {clean_vobiz_to} (cid={call_uuid}) via Vobiz API: HTTP {resp.status_code} - {data}")

            if isinstance(data, dict) and data.get("request_uuid"):
                v_req_uuid = data.get("request_uuid")
                try:
                    with SessionLocal() as db_s2:
                        s_rec = db_s2.query(CallSession).filter(CallSession.id == call_uuid).first()
                        if s_rec:
                            c_f = dict(s_rec.custom_fields or {})
                            c_f["vobiz_call_uuid"] = v_req_uuid
                            s_rec.custom_fields = c_f
                            db_s2.commit()
                except Exception as cf_err:
                    print(f"[Vobiz Custom Fields Save Warning] {cf_err}")

            if resp.status_code not in (200, 201):
                raise HTTPException(status_code=resp.status_code, detail=f"Vobiz API error: {resp.text}")

            return {"success": True, "provider": "vobiz", "data": data, "call_id": call_uuid}
        except HTTPException:
            raise
        except Exception as err:
            print(f"[Vobiz Outbound Call Error]: {err}")
            raise HTTPException(status_code=500, detail=str(err))

    # 2. Secondary Provider: Exotel API
    account_sid = os.environ.get("EXOTEL_ACCOUNT_SID", "snazzyitsolutions1")
    api_key = os.environ.get("EXOTEL_API_KEY")
    api_token = os.environ.get("EXOTEL_API_TOKEN")
    caller_id = os.environ.get("EXOTEL_VIRTUAL_NUMBER", "08047283364")

    if not api_key or not api_token:
        raise HTTPException(status_code=500, detail="Telephony credentials missing (neither Vobiz nor Exotel configured)")

    clean_to = to_phone.replace(" ", "").replace("+91", "0")
    auth_str = base64.b64encode(f"{api_key}:{api_token}".encode()).decode()
    exotel_url = f"https://api.exotel.com/v1/Accounts/{account_sid}/Calls/connect.json"
    flow_url = f"https://my.exotel.com/{account_sid}/exoml/start_voice/1337835"

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                exotel_url,
                headers={
                    "Authorization": f"Basic {auth_str}",
                    "Content-Type": "application/x-www-form-urlencoded"
                },
                data={
                    "From": clean_to,
                    "To": caller_id,
                    "CallerId": caller_id,
                    "Url": flow_url,
                    "CallType": "trans",
                    "TimeLimit": "3600",
                    "TimeOut": "30"
                }
            )

        data = resp.json()
        print(f"[Exotel Outbound Call] Dialed {clean_to} via Flow {flow_url}: HTTP {resp.status_code}")

        # Record call session in CRM DB
        from services.dashboard.app.database import SessionLocal
        from services.dashboard.app.models import CallSession, Organization, Contact
        with SessionLocal() as db_s:
            org = db_s.query(Organization).first()
            org_id = org.id if org else str(uuid.uuid4())
            contact = db_s.query(Contact).filter(Contact.phone_number == to_phone).first()
            session_rec = CallSession(
                id=str(uuid.uuid4()),
                organization_id=org_id,
                contact_id=contact.id if contact else None,
                provider="exotel",
                direction="outbound",
                from_number=caller_id,
                to_number=to_phone,
                status="in_progress",
                duration_s=0.0
            )
            db_s.add(session_rec)
            db_s.commit()

        if resp.status_code not in (200, 201):
            raise HTTPException(status_code=resp.status_code, detail=f"Exotel API error: {resp.text}")

        return {"success": True, "provider": "exotel", "data": data}

    except HTTPException:
        raise
    except Exception as err:
        print(f"[Exotel Outbound Call Error]: {err}")
        raise HTTPException(status_code=500, detail=str(err))

    except HTTPException:
        raise
    except Exception as err:
        print(f"[Exotel Outbound Call Error]: {err}")
        raise HTTPException(status_code=500, detail=str(err))

# Serve Frontend Static Build
FRONTEND_DIST = os.path.join(WORKSPACE_DIR, "frontend", "dist")
if not os.path.exists(FRONTEND_DIST):
    FRONTEND_DIST = os.path.join(LEGACY_DIR, "frontend", "dist")

if os.path.exists(FRONTEND_DIST):
    app.mount("/assets", StaticFiles(directory=os.path.join(FRONTEND_DIST, "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        if full_path.startswith("api") or full_path.startswith("ws"):
            raise HTTPException(status_code=404, detail="API route not found")
        file_path = os.path.join(FRONTEND_DIST, full_path)
        if os.path.exists(file_path) and os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(FRONTEND_DIST, "index.html"))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("services.dashboard.app.main:app", host=settings.HOST, port=settings.PORT, reload=False)
