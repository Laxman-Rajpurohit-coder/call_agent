from fastapi import APIRouter
from services.dashboard.app.services.health_service import check_all_services

router = APIRouter(prefix="/health", tags=["Health"])

@router.get("")
async def get_health():
    services = await check_all_services()
    all_healthy = all(s["status"] == "healthy" for s in services)
    return {
        "status": "healthy" if all_healthy else "degraded",
        "services": services
    }
