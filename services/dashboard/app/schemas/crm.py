from typing import Optional, List, Any, Dict
from datetime import datetime
from pydantic import BaseModel, ConfigDict

class ContactBase(BaseModel):
    phone_number: str
    name: Optional[str] = None
    email: Optional[str] = None
    status: Optional[str] = "lead"
    preferred_language: Optional[str] = "hi"
    custom_fields: Optional[Dict[str, Any]] = {}

class ContactCreate(ContactBase):
    pass

class ContactResponse(ContactBase):
    id: str
    organization_id: str
    last_called_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

class CallInteractionResponse(BaseModel):
    id: str
    call_id: str
    intent_detected: Optional[str] = None
    confidence: Optional[float] = 0.0
    ai_summary: Optional[str] = None
    human_handoff_requested: bool = False
    followup_required: bool = False
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class CallSessionResponse(BaseModel):
    id: str
    organization_id: str
    contact_id: Optional[str] = None
    provider: str
    direction: str
    from_number: str
    to_number: str
    status: str
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    duration_s: float
    recording_url: Optional[str] = None
    transcript: List[Dict[str, Any]] = []
    created_at: datetime
    contact: Optional[ContactResponse] = None
    interactions: List[CallInteractionResponse] = []

    model_config = ConfigDict(from_attributes=True)
