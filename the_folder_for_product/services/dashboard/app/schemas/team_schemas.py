from typing import Optional, List, Any, Dict
from datetime import datetime
from pydantic import BaseModel, ConfigDict

class TeamMemberBase(BaseModel):
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    role: Optional[str] = 'Sales Agent'
    is_active: Optional[bool] = True
    pin_code: Optional[str] = "1234"
    status: Optional[str] = "available"
    sip_extension: Optional[str] = "101"
    sip_password: Optional[str] = "101pass"
    avatar_url: Optional[str] = None
    daily_call_target: Optional[float] = 50.0
    shift_name: Optional[str] = "Morning Shift"

class TeamMemberCreate(TeamMemberBase):
    pass

class TeamMemberResponse(TeamMemberBase):
    id: str
    organization_id: str
    assigned_leads_count: float
    status_updated_at: Optional[datetime] = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

class TeamMemberStats(BaseModel):
    id: str
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    role: str
    is_active: bool
    status: Optional[str] = "available"
    sip_extension: Optional[str] = "101"
    shift_name: Optional[str] = "Morning Shift"
    daily_call_target: Optional[float] = 50.0
    assigned_leads: int
    total_calls: int
    incoming_calls: int
    outgoing_calls: int
    total_talk_time_s: float
    completed_tasks: int
    daily_target: Optional[int] = 200
    target_progress_pct: Optional[float] = 0.0

