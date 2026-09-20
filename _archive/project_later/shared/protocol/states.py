"""
Canonical call states. Every service (gateway, STT, LLM, TTS) imports
this instead of using string literals, so a typo can't silently create
a new, unrecognized state.
"""

from enum import Enum


class CallState(str, Enum):
    CREATED = "CREATED"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    LISTENING = "LISTENING"
    USER_SPEAKING = "USER_SPEAKING"
    PROCESSING_STT = "PROCESSING_STT"
    PROCESSING_LLM = "PROCESSING_LLM"
    PROCESSING_TTS = "PROCESSING_TTS"
    AI_SPEAKING = "AI_SPEAKING"
    TRANSFERRING = "TRANSFERRING"
    ENDING = "ENDING"
    ENDED = "ENDED"
    FAILED = "FAILED"


# States from which a call is allowed to transition to HUMAN handoff.
# Kept explicit rather than "any state can transfer" so the gateway has
# one place to check instead of scattering the rule across handlers.
TRANSFERABLE_STATES = {
    CallState.LISTENING,
    CallState.USER_SPEAKING,
    CallState.PROCESSING_STT,
    CallState.PROCESSING_LLM,
    CallState.PROCESSING_TTS,
    CallState.AI_SPEAKING,
}
