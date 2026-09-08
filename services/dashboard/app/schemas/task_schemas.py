from typing import Optional, List, Any, Dict
from datetime import datetime
from pydantic import BaseModel, ConfigDict

class TaskBase(BaseModel):
    title: str
    description: Optional[str] = None
    contact_id: Optional[str] = None
    assigned_to_id: Optional[str] = None
    due_at: Optional[datetime] = None
    custom_inquiry_data: Optional[Dict[str, Any]] = {}

class TaskCreate(TaskBase):
    pass

class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    assigned_to_id: Optional[str] = None
    due_at: Optional[datetime] = None

class TaskResponse(TaskBase):
    id: str
    organization_id: str
    status: str
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

class ReminderCreate(BaseModel):
    contact_id: Optional[str] = None
    task_id: Optional[str] = None
    note: str
    remind_at: datetime

class ReminderResponse(BaseModel):
    id: str
    note: str
    remind_at: datetime
    is_triggered: bool
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)
