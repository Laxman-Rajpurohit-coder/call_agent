"""
Canonical call events. These are what gets published to logs/metrics
and what worker services react to. Keeping this as one shared enum
means the gateway and every worker agree on vocabulary — a STT worker
finishing a job always emits STT_COMPLETED, never "stt_done" in one
service and "transcription_finished" in another.
"""

from enum import Enum


class CallEvent(str, Enum):
    CALL_STARTED = "CALL_STARTED"
    AUDIO_RECEIVED = "AUDIO_RECEIVED"
    USER_SPEECH_STARTED = "USER_SPEECH_STARTED"
    USER_SPEECH_ENDED = "USER_SPEECH_ENDED"

    STT_REQUESTED = "STT_REQUESTED"
    STT_COMPLETED = "STT_COMPLETED"
    STT_FAILED = "STT_FAILED"

    LLM_REQUESTED = "LLM_REQUESTED"
    LLM_TOKEN = "LLM_TOKEN"
    LLM_COMPLETED = "LLM_COMPLETED"
    LLM_FAILED = "LLM_FAILED"

    TTS_REQUESTED = "TTS_REQUESTED"
    TTS_AUDIO_READY = "TTS_AUDIO_READY"
    TTS_FAILED = "TTS_FAILED"

    AI_SPEECH_STARTED = "AI_SPEECH_STARTED"
    AI_SPEECH_ENDED = "AI_SPEECH_ENDED"

    HUMAN_HANDOFF_REQUESTED = "HUMAN_HANDOFF_REQUESTED"
    HUMAN_HANDOFF_COMPLETED = "HUMAN_HANDOFF_COMPLETED"

    CALL_ENDED = "CALL_ENDED"
    CALL_FAILED = "CALL_FAILED"

    # Admission control — a call that never got a worker slot
    CALL_REJECTED_AT_CAPACITY = "CALL_REJECTED_AT_CAPACITY"
