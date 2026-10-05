"""
Explicit escalation policy. Deliberately simple rules for now — the
point isn't sophistication yet, it's that "should this go to a human"
is a real, testable function that exists from day one instead of a
vague TODO. Swap the body for a classifier/policy engine later without
changing anything that calls this.
"""

from shared.protocol import EscalationLevel

# Phrases that should always route to a human, regardless of STT
# confidence. Keep this list short and specific — it's a safety net,
# not the primary mechanism.
_ALWAYS_ESCALATE_PHRASES = (
    "speak to a human",
    "talk to a person",
    "talk to an agent",
    "complaint",
    "cancel my",
    "refund",
    "बात कराओ",
    "इंसान से बात",
    "अधिकारी से बात",
    "टीम से बात",
    "रसीद",
    "दान का रिकॉर्ड",
    "स्टेटस",
    "पुष्टि",
    "receipt",
    "donation record",
    "status",
    "confirmation",
)

# Below this, we don't trust the transcript enough to act on it.
STT_CONFIDENCE_LOW = 0.20
# Below this, ask a clarifying question rather than answer directly.
STT_CONFIDENCE_MEDIUM = 0.35


def classify(transcript: str, stt_confidence: float) -> EscalationLevel:
    lowered = transcript.lower()

    if any(phrase in lowered for phrase in _ALWAYS_ESCALATE_PHRASES):
        return EscalationLevel.LOW

    # Low STT confidence should be MEDIUM (clarify / proceed with conversational AI),
    # never LOW (which triggers an immediate phone line transfer to an Asterisk extension).
    if stt_confidence < STT_CONFIDENCE_LOW:
        return EscalationLevel.MEDIUM

    if stt_confidence < STT_CONFIDENCE_MEDIUM:
        return EscalationLevel.MEDIUM

    return EscalationLevel.HIGH
