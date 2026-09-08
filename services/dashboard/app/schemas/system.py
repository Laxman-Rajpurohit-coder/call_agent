from typing import Optional, List, Dict, Any
from pydantic import BaseModel

class ServiceHealth(BaseModel):
    name: str
    port: int
    url: str
    status: str # "healthy", "degraded", "offline"
    latency_ms: Optional[float] = None
    details: Optional[Dict[str, Any]] = None

class SystemOverview(BaseModel):
    total_calls: int
    active_calls: int
    completed_calls: int
    human_handoffs: int
    total_contacts: int
    overall_pass_rate: float
    services: List[ServiceHealth]

class TTSRequest(BaseModel):
    text: str = "Namaste, welcome to Superfone AI Voice Bot."
    voice: str = "hi_pratham"
    speed: float = 1.0
    volume_gain_db: float = 0.0
    fade_in_ms: float = 4.0
