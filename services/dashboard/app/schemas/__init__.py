from services.dashboard.app.schemas.crm import ContactCreate, ContactResponse, CallSessionResponse, CallInteractionResponse
from services.dashboard.app.schemas.campaign import CampaignCreate, CampaignResponse, CampaignProgress
from services.dashboard.app.schemas.system import ServiceHealth, SystemOverview, TTSRequest

__all__ = [
    "ContactCreate", "ContactResponse", "CallSessionResponse", "CallInteractionResponse",
    "CampaignCreate", "CampaignResponse", "CampaignProgress",
    "ServiceHealth", "SystemOverview", "TTSRequest"
]
