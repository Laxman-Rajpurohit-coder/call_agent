import uuid
from dataclasses import dataclass, field
from typing import Any, Optional, Dict
from datetime import datetime

@dataclass
class ProviderResult:
    success: bool
    provider: str
    output: Any
    latency_ms: float
    role: str = "primary"  # "primary" or "backup"
    backup_used: bool = False
    backup_reason: Optional[str] = None
    cost_usd: float = 0.0
    usage: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    request_id: Optional[str] = field(default_factory=lambda: str(uuid.uuid4()))

class BaseProvider:
    def __init__(self, name: str, is_cloud: bool = True):
        self.name = name
        self.is_cloud = is_cloud
