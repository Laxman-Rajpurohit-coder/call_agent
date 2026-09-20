from fastapi import APIRouter
from services.dashboard.app.services.load_test_service import get_load_test_summaries

router = APIRouter(prefix="/load-tests", tags=["Load Tests"])

@router.get("")
async def list_load_tests():
    return get_load_test_summaries()
