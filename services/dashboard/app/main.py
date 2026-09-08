import os
import sys
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

ROOT_DIR = r"c:\daily_works\superfone_call"
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

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

# Serve Call Recordings Static Directory
RECORDINGS_DIR = os.path.join(ROOT_DIR, "recordings")
os.makedirs(RECORDINGS_DIR, exist_ok=True)
app.mount("/recordings", StaticFiles(directory=RECORDINGS_DIR), name="recordings")

# Serve Frontend Static Build
FRONTEND_DIST = os.path.join(ROOT_DIR, "frontend", "dist")
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
