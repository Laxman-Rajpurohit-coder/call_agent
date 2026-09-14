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

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize DB tables & migrations
    Base.metadata.create_all(bind=engine)
    run_migrations()
    
    # Start background log tailer and reminder checker tasks
    tailer_task = asyncio.create_task(log_tailer_task())
    reminder_task = asyncio.create_task(reminder_checker_task())
    yield
    tailer_task.cancel()
    reminder_task.cancel()

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

@app.post("/api/telephony/outbound-call")
@app.post("/api/v1/telephony/outbound-call")
async def handle_exotel_outbound_call(req: ExotelOutboundRequest):
    """
    Triggers automated outbound cellular/PSTN call via Exotel API
    routing to the Voicebot Flow (Flow 1337835).
    """
    to_phone = req.to.strip() if req.to else ""
    if not to_phone:
        raise HTTPException(status_code=400, detail="Recipient phone number (to) is required.")

    account_sid = os.environ.get("EXOTEL_ACCOUNT_SID", "snazzyitsolutions1")
    api_key = os.environ.get("EXOTEL_API_KEY")
    api_token = os.environ.get("EXOTEL_API_TOKEN")
    caller_id = os.environ.get("EXOTEL_VIRTUAL_NUMBER", "08047283364")

    if not api_key or not api_token:
        raise HTTPException(status_code=500, detail="Exotel API key or token missing in .env")

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
        db_s = SessionLocal()
        try:
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
        except Exception as db_err:
            print(f"[Exotel Outbound DB Log Warning]: {db_err}")
        finally:
            db_s.close()

        if resp.status_code not in (200, 201):
            raise HTTPException(status_code=resp.status_code, detail=f"Exotel API error: {resp.text}")

        return {"success": True, "data": data}

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
