from typing import Optional, List, Any
from datetime import datetime
from pydantic import BaseModel, ConfigDict

class WhatsAppSendRequest(BaseModel):
    contact_id: Optional[str] = None
    phone_number: str
    message_text: str

class WhatsAppMessageResponse(BaseModel):
    id: str
    contact_id: Optional[str] = None
    phone_number: str
    direction: str
    message_text: str
    status: str
    timestamp: datetime
    model_config = ConfigDict(from_attributes=True)
