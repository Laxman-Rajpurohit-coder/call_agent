from typing import Optional, List, Any, Dict
from datetime import datetime
from pydantic import BaseModel, ConfigDict

class ContactBase(BaseModel):
    phone_number: str
    name: Optional[str] = None
    email: Optional[str] = None
    status: Optional[str] = "lead"
    preferred_language: Optional[str] = "hi"
    company: Optional[str] = None
    tags: Optional[List[str]] = []
    is_archived: Optional[bool] = False
    is_blocked: Optional[bool] = False
    ai_profile: Optional[Dict[str, Any]] = None
    lead_owner_id: Optional[str] = None
    merged_into_id: Optional[str] = None
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

class ContactNoteCreate(BaseModel):
    note: str
    disposition: Optional[str] = None
    sentiment: Optional[str] = None
    remind_in_minutes: Optional[int] = None
    agent_name: Optional[str] = None

class ContactNoteResponse(BaseModel):
    id: str
    contact_id: str
    organization_id: str
    agent_id: Optional[str] = None
    agent_name: Optional[str] = None
    note: str
    disposition: Optional[str] = None
    sentiment: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

class CallInteractionResponse(BaseModel):
    id: str
    call_id: str
    intent_detected: Optional[str] = None
    confidence: Optional[float] = 0.0
    ai_summary: Optional[str] = None
    human_handoff_requested: bool = False
    followup_required: bool = False
    # Unified intent / lead labelling (call_analysis.py) - Optional: old rows have NULLs
    lead_label: Optional[str] = None
    evidence_quote: Optional[str] = None
    sentiment: Optional[str] = None
    model_name: Optional[str] = None
    prompt_version: Optional[str] = None
    followup_date: Optional[datetime] = None
    is_agent_corrected: Optional[bool] = False
    agent_notes: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class CallHandlerSchema(BaseModel):
    type: str = "AI"  # "AI" | "HUMAN" | "TRANSFERRING" | "UNKNOWN"
    id: Optional[str] = None
    name: Optional[str] = "Superfone AI"
    role: Optional[str] = "AI Agent"

class CallMediaStateSchema(BaseModel):
    rtp: str = "CONNECTED"  # "CONNECTED" | "RECEIVING" | "SILENT" | "DEGRADED" | "DISCONNECTED"
    codec: Optional[str] = "G.711 PCMU"
    sample_rate: Optional[int] = 8000
    last_packet_at: Optional[str] = None

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
    connected_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    duration_s: float
    recording_url: Optional[str] = None
    transcript: List[Dict[str, Any]] = []
    created_at: datetime
    contact: Optional[ContactResponse] = None
    interactions: List[CallInteractionResponse] = []
    
    # Handler & Media Attribution
    handler: Optional[CallHandlerSchema] = None
    media: Optional[CallMediaStateSchema] = None
    vad_state: Optional[str] = "LISTENING"
    handled_by_user_id: Optional[str] = None
    handled_by_name: Optional[str] = None
    agent_name: Optional[str] = None
    voice_model: Optional[str] = None
    handoff_status: Optional[str] = "NONE"
    handoff_reason: Optional[str] = None
    ai_summary: Optional[str] = None
    analysis_status: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
