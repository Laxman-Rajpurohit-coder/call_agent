from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from services.dashboard.app.database import get_db
from services.dashboard.app.models import CallSession, Contact, CallInteraction
from services.dashboard.app.services.health_service import check_all_services
from services.dashboard.app.services.eval_service import get_evaluation_reports

router = APIRouter(prefix="/overview", tags=["Overview"])

@router.get("")
async def get_overview(db: Session = Depends(get_db)):
    services = await check_all_services()
    total_calls = db.query(CallSession).count()
    active_calls = db.query(CallSession).filter(CallSession.status == "in_progress").count()
    completed_calls = db.query(CallSession).filter(CallSession.status == "completed").count()
    human_handoffs = db.query(CallInteraction).filter(CallInteraction.human_handoff_requested == True).count()
    total_contacts = db.query(Contact).count()

    reports = get_evaluation_reports()
    avg_pass_rate = 100.0
    if reports:
        avg_pass_rate = round(sum(r["pass_rate"] for r in reports) / len(reports) * 100.0, 1)

    return {
        "total_calls": total_calls,
        "active_calls": active_calls,
        "completed_calls": completed_calls,
        "human_handoffs": human_handoffs,
        "total_contacts": total_contacts,
        "overall_pass_rate": avg_pass_rate,
        "services": services
    }
