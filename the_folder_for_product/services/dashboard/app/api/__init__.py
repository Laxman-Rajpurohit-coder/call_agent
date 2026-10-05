from fastapi import APIRouter
from services.dashboard.app.api.health import router as health_router
from services.dashboard.app.api.overview import router as overview_router
from services.dashboard.app.api.calls import router as calls_router
from services.dashboard.app.api.contacts import router as contacts_router
from services.dashboard.app.api.campaigns import router as campaigns_router
from services.dashboard.app.api.evaluations import router as evaluations_router
from services.dashboard.app.api.load_tests import router as load_tests_router
from services.dashboard.app.api.voice import router as voice_router
from services.dashboard.app.api.websocket import router as ws_router
from services.dashboard.app.api.leads import router as leads_router
from services.dashboard.app.api.tasks import router as tasks_router
from services.dashboard.app.api.reminders import router as reminders_router
from services.dashboard.app.api.whatsapp import router as whatsapp_router
from services.dashboard.app.api.team import router as team_router
from services.dashboard.app.api.auth import router as auth_router
from services.dashboard.app.api.tools import router as tools_router
from services.dashboard.app.api.portals import router as portals_router

from services.dashboard.app.api.incoming_configs import router as incoming_configs_router
api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(overview_router)
api_router.include_router(calls_router)
api_router.include_router(contacts_router)
api_router.include_router(campaigns_router)
api_router.include_router(evaluations_router)
api_router.include_router(load_tests_router)
api_router.include_router(voice_router)
api_router.include_router(ws_router)
api_router.include_router(auth_router, prefix="/auth", tags=["Auth"])
api_router.include_router(portals_router)
api_router.include_router(leads_router, prefix="/leads", tags=["Leads"])
api_router.include_router(tasks_router, prefix="/tasks", tags=["Tasks"])
api_router.include_router(reminders_router, prefix="/reminders", tags=["Reminders"])
api_router.include_router(whatsapp_router, prefix="/whatsapp", tags=["WhatsApp"])
api_router.include_router(team_router, prefix="/team", tags=["Team"])
api_router.include_router(tools_router)



api_router.include_router(incoming_configs_router)