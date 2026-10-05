"""
The actual payloads that move through queues between the call gateway
and the STT/LLM/TTS worker pools. Every job carries call_id, session_id,
and tenant_id so results can always be routed back to the right call
and every log line can be correlated, even once there are hundreds of
calls in flight across multiple worker boxes.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import uuid4

from .states import CallState


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class CallSession:
    call_id: str
    tenant_id: str
    bot_id: Optional[str] = None
    system_prompt: Optional[str] = None
    greeting: Optional[str] = None
    voice_model: Optional[str] = None
    primary_language: Optional[str] = None
    call_direction: Optional[str] = "inbound"
    session_id: str = field(default_factory=lambda: str(uuid4()))
    state: CallState = CallState.CREATED
    started_at: datetime = field(default_factory=_now)
    ended_at: Optional[datetime] = None


class EscalationLevel(str, Enum):
    """Confidence-based routing decision — not vague 'low confidence',
    an explicit three-way rule every call gets classified into."""
    HIGH = "HIGH"        # AI answers directly
    MEDIUM = "MEDIUM"    # AI asks a clarifying question first
    LOW = "LOW"          # route straight to human handoff


@dataclass
class STTJob:
    call_id: str
    tenant_id: str
    audio_pcm16_8k: bytes
    primary_language: Optional[str] = None
    requested_at: datetime = field(default_factory=_now)


@dataclass
class STTResult:
    call_id: str
    text: str
    confidence: float
    latency_ms: float


@dataclass
class LLMJob:
    call_id: str
    tenant_id: str
    transcript: str
    conversation_history: list[dict]  # [{"role": "user"/"assistant", "content": ...}]
    system_prompt: Optional[str] = None
    escalation: EscalationLevel = EscalationLevel.LOW
    requested_at: datetime = field(default_factory=_now)


@dataclass
class LLMResult:
    call_id: str
    reply_text: str
    escalation: EscalationLevel
    latency_ms: float
    first_token_ms: Optional[float] = None


@dataclass
class TTSJob:
    call_id: str
    tenant_id: str
    text: str
    voice_id: str = "en_US-lessac-medium"
    requested_at: datetime = field(default_factory=_now)


@dataclass
class TTSResult:
    call_id: str
    audio_pcm16_8k: bytes
    latency_ms: float
