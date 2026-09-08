from fastapi import APIRouter, HTTPException
from services.dashboard.app.services.eval_service import get_evaluation_reports, get_evaluation_detail

router = APIRouter(prefix="/evaluations", tags=["Evaluations"])

@router.get("")
async def list_evaluations():
    return get_evaluation_reports()

@router.get("/{run_id}")
async def get_evaluation(run_id: str):
    detail = get_evaluation_detail(run_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Evaluation report not found")
    return detail
