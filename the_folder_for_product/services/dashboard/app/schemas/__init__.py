from services.dashboard.app.schemas.crm import (
    ContactCreate, ContactResponse, ContactNoteCreate, ContactNoteResponse,
    CallSessionResponse, CallInteractionResponse
)
from services.dashboard.app.schemas.campaign import CampaignCreate, CampaignResponse, CampaignProgress, CampaignContactDetail
from services.dashboard.app.schemas.system import ServiceHealth, SystemOverview, TTSRequest

__all__ = [
    "ContactCreate", "ContactResponse", "ContactNoteCreate", "ContactNoteResponse",
    "CallSessionResponse", "CallInteractionResponse",
    "CampaignCreate", "CampaignResponse", "CampaignProgress", "CampaignContactDetail",
    "ServiceHealth", "SystemOverview", "TTSRequest"
]
