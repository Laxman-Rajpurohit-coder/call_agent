from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, ConfigDict

class CampaignBase(BaseModel):
    name: str
    description: Optional[str] = None
    type: str = "SCRIPT" # SCRIPT, AI, HYBRID
    script_content: Optional[str] = None
    voice_model: str = "hi_pratham"
    max_concurrency: int = 5
    calls_per_minute: int = 20
    max_retries: int = 2

class CampaignCreate(CampaignBase):
    contact_ids: Optional[List[str]] = []
    custom_phone_numbers: Optional[List[str]] = []
    assigned_agent_id: Optional[str] = None
    assigned_agent_name: Optional[str] = None

class CampaignResponse(CampaignBase):
    id: str
    status: str
    contact_count: Optional[int] = 0
    assigned_agent_id: Optional[str] = None
    assigned_agent_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

class CampaignContactDetail(BaseModel):
    id: str
    contact_id: str
    name: str
    phone_number: str
    email: Optional[str] = None
    status: str
    attempt_count: int
    last_attempt_at: Optional[str] = None
    final_outcome: Optional[str] = None

class CampaignProgress(BaseModel):
    campaign_id: str
    total_contacts: int
    pending: int
    queued: int
    calling: int
    answered: int
    completed: int
    no_answer: int
    failed: int
    progress_percentage: float
