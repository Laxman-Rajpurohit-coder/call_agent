"""
Unified post-call intent & lead labelling engine.

One function - ``analyze_call`` - is the single place where a finished call is turned
into CRM data (intent, lead label, evidence quote, summary, follow-up task).  Every
telephony path (Twilio/Exotel gateway, Asterisk AudioSocket gateway, campaign runner)
must call ``schedule_call_analysis(call_id)`` when a call ends.

Design rules (see the implementation plan):
  * The LLM decides the label.  Keyword rules are only *hints* passed to the LLM and a
    reason to fall back to ``needs_review`` - they never silently override the model.
  * An answer is only trusted if the evidence quote is really in the caller's speech.
  * Anything invalid / unsure becomes ``needs_review`` - a label is never guessed.
  * ``call_sessions.analysis_status`` (PENDING -> RUNNING -> DONE | FAILED) makes the job
    idempotent and retryable after a crash (see ``retry_pending_analyses``).
  * Pure logic (parsing / validation) is kept free of DB and network imports so it can
    be unit-tested on its own.  DB models are imported lazily inside the functions.
"""

import asyncio
import json
import logging
import os
import re
import string
import threading
import unicodedata
import uuid
from datetime import datetime, timedelta
from typing import Any, Awaitable, Callable, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("call_analysis")

# --------------------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------------------

PROMPT_VERSION = "v1.0"

# Tried in order until one answers.  Override with ANALYSIS_LLM_MODELS="model1,model2".
LLM_MODELS: List[str] = [
    m.strip()
    for m in os.environ.get("ANALYSIS_LLM_MODELS", "qwen/qwen3.8-27b,llama-3.3-70b-versatile").split(",")
    if m.strip()
]
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

# Model confidence is NOT calibrated - treat as a weak signal until the hand-labelled
# test set (tests/fixtures/transcript_test_set.json) has been benchmarked.
CONFIDENCE_MIN = float(os.environ.get("ANALYSIS_CONFIDENCE_MIN", "0.5"))
STALE_RUNNING_MINUTES = 10

DEFAULT_INTENTS: List[str] = [
    "price_query", "site_visit", "complaint", "callback_request",
    "working_hours", "general_info", "human_transfer", "unknown",
]
DEFAULT_LEAD_LABELS: List[str] = [
    "hot", "warm", "cold", "not_interested", "callback",
    "wrong_number", "do_not_call", "no_conversation", "needs_review",
]
MANDATORY_LABELS = ("needs_review", "no_conversation")
SENTIMENTS = ("POSITIVE", "NEUTRAL", "NEGATIVE", "FRUSTRATED")

LABEL_CRITERIA: Dict[str, str] = {
    "hot": "caller explicitly asks to book an appointment, buy, visit, or asks for an urgent call/action.",
    "warm": "caller asks about prices, product/treatment details, hours or location but has not committed.",
    "cold": "caller is polite but vague; no clear intention to act.",
    "not_interested": "caller explicitly refuses or declines.",
    "callback": "caller asks to be called back at another time (busy right now).",
    "wrong_number": "caller says this is a wrong number / they are not the person being sought.",
    "do_not_call": "caller explicitly asks to stop calling / remove their number.",
    "needs_review": "use this whenever you cannot decide confidently.",
}

# lead label -> Contact.status
LABEL_TO_CONTACT_STATUS: Dict[str, str] = {
    "hot": "HOT_LEAD",
    "warm": "WARM_LEAD",
    "cold": "COLD_LEAD",
    "not_interested": "NOT_INTERESTED",
    "callback": "CALLBACK_REQUESTED",
    "wrong_number": "WRONG_NUMBER",
    "do_not_call": "DO_NOT_CALL",
}
# Contacts in these states must never be dialled by a campaign.
DO_NOT_CALL_STATUSES: Set[str] = {"DO_NOT_CALL", "WRONG_NUMBER", "OPT_OUT"}
# Only contacts still "in the funnel" may be re-labelled; won/converted customers are left alone.
LEAD_STATUSES: Set[str] = {
    "", "LEAD", "NEW", "HOT_LEAD", "WARM_LEAD", "COLD_LEAD",
    "NOT_INTERESTED", "CALLBACK_REQUESTED",
}
TASK_LABELS = {"hot", "warm", "callback"}
NO_TASK_LABELS = {"do_not_call", "wrong_number", "not_interested", "no_conversation", "needs_review"}

CALLER_ROLES = {"user", "caller", "customer", "human", "client"}
ASSISTANT_ROLES = {"assistant", "agent", "bot", "ai"}
NON_AGENT_ROLES = {"OWNER", "ADMIN", "MANAGER", "VIEWER"}  # never receive auto-assigned leads

LlmCall = Callable[[List[Dict[str, str]]], Awaitable[Tuple[Optional[str], Optional[str]]]]

# --------------------------------------------------------------------------------------
# Pure helpers (no DB / network)
# --------------------------------------------------------------------------------------

_PUNCT = re.compile("[" + re.escape(string.punctuation) + "\u0964\u0965\u2026\u201c\u201d\u2018\u2019\u2014\u2013" + "]")


def clean_reasoning_tokens(text: str) -> str:
    """Strip <think>...</think> blocks (Qwen-style reasoning) before parsing."""
    if not text:
        return ""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<think>.*$", "", text, flags=re.DOTALL | re.IGNORECASE)  # unterminated block
    return text.strip()


def _norm(text: Any) -> str:
    """Lower-case, drop punctuation, collapse whitespace - used for quote matching."""
    s = unicodedata.normalize("NFC", str(text or "")).lower()
    s = _PUNCT.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()


def caller_turns(transcript: Any) -> List[str]:
    """Utterances spoken by the caller (not the AI)."""
    turns: List[str] = []
    for t in transcript or []:
        if not isinstance(t, dict):
            continue
        role = str(t.get("role", "")).lower()
        content = str(t.get("content") or t.get("text") or "").strip()
        if role in CALLER_ROLES and content:
            turns.append(content)
    return turns


def is_short_call(transcript: Any) -> bool:
    """True when there is nothing meaningful to classify (caller < 2 turns or < 15 words total)."""
    if len(caller_turns(transcript)) < 2:
        return True
    total_words = 0
    for t in transcript or []:
        if isinstance(t, dict) and str(t.get("role", "")).lower() != "system":
            total_words += len(str(t.get("content") or t.get("text") or "").split())
    return total_words < 15


_DNC_PATTERNS = [
    r"\bdo not call\b", r"\bdon'?t call\b", r"\bdont call\b", r"\bstop calling\b",
    r"\bremove (me|my number)\b", r"\bunsubscribe\b", r"\bopt[- ]?out\b",
    r"call\s+(mat|na|nahi|nahin)\s+kar", r"phone\s+(mat|na)\s+kar",
    r"(mujhe|humein|hume)\s+call\s+(mat|na)", r"number\s+(hata|delete|remove)",
    r"\u0915\u0949\u0932\s*\u092e\u0924", r"\u092b\u094b\u0928\s*\u092e\u0924",
    r"\u092b\u093c\u094b\u0928\s*\u092e\u0924", r"\u0915\u0949\u0932\s*\u0928\s*\u0915\u0930",
]
_HUMAN_PATTERNS = [
    r"\bhuman\b", r"real person", r"(talk|speak) to (a |an )?(person|agent|manager|someone)",
    r"\bmanager\b", r"(insaan|insan|aadmi|manager|agent|kisi)\s+se\s+baat",
    r"\u0907\u0902\u0938\u093e\u0928", r"\u092e\u0948\u0928\u0947\u091c\u0930",
    r"\u0915\u093f\u0938\u0940 \u0938\u0947 \u092c\u093e\u0924",
]


def keyword_hints(caller_text: str) -> Set[str]:
    """Cheap keyword scan.  Results are HINTS only - they never decide a label by themselves."""
    text = (caller_text or "").lower()
    hints: Set[str] = set()
    if any(re.search(p, text) for p in _DNC_PATTERNS):
        hints.add("do_not_call")
    if any(re.search(p, text) for p in _HUMAN_PATTERNS):
        hints.add("human_transfer")
    return hints


def quote_in_caller_speech(quote: str, caller_lines: List[str]) -> bool:
    """The evidence quote must literally come from the caller (ignoring case/punctuation)."""
    nq = _norm(quote)
    if len(nq) < 2:
        return False
    if any(nq in _norm(line) for line in caller_lines):
        return True
    return nq in _norm(" ".join(caller_lines))


def build_messages(
    transcript: Any,
    intents: List[str],
    labels: List[str],
    org_name: str = "the business",
    industry: str = "",
    hints: Optional[Set[str]] = None,
) -> List[Dict[str, str]]:
    criteria = "\n".join(f"- {l}: {LABEL_CRITERIA.get(l, '(custom label)')}" for l in labels)
    hint_line = ""
    if hints:
        hint_line = (
            "\nAutomatic keyword hints (may be false alarms, verify against the conversation): "
            + ", ".join(sorted(hints)) + "\n"
        )
    system = (
        f"You are a call-analysis engine for {org_name}" + (f" ({industry})" if industry else "") + ".\n"
        "You receive a phone conversation between an AI assistant and a CALLER (Hindi, English or Hinglish).\n"
        "Classify the CALLER. Reply with ONE JSON object only - no markdown, no commentary.\n\n"
        f"Allowed intents: {json.dumps(intents)}\n"
        f"Allowed lead labels: {json.dumps(labels)}\n"
        f"Label criteria:\n{criteria}\n\n"
        "JSON format:\n"
        '{"intent": "<allowed intent>", "lead_label": "<allowed label>", "confidence": <0.0-1.0>, '
        '"evidence_quote": "<exact words spoken by the CALLER>", "ai_summary": "<1-2 sentences, English>", '
        '"needs_human": <true|false>, "sentiment": "POSITIVE|NEUTRAL|NEGATIVE|FRUSTRATED", '
        '"followup_days": <integer or null>}\n\n'
        "Rules:\n"
        "- evidence_quote MUST be copied verbatim from a CALLER line, in the original language/script. "
        "Never translate it and never quote the assistant.\n"
        "- If you are not sure, use lead_label \"needs_review\".\n"
        "- Use only values from the allowed lists."
        + hint_line
    )
    lines: List[str] = []
    for t in transcript or []:
        if not isinstance(t, dict):
            continue
        role = str(t.get("role", "")).lower()
        content = str(t.get("content") or t.get("text") or "").strip()
        if not content:
            continue
        if role in CALLER_ROLES:
            lines.append(f"CALLER: {content}")
        elif role in ASSISTANT_ROLES:
            lines.append(f"ASSISTANT: {content}")
    body = "\n".join(lines)
    if len(body) > 12000:
        body = body[:2000] + "\n...\n" + body[-10000:]
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": "Conversation:\n" + body},
    ]


def parse_llm_json(raw: Optional[str]) -> Optional[Dict[str, Any]]:
    """Extract the JSON object from an LLM reply (handles <think>, ``` fences, extra prose)."""
    if not raw:
        return None
    text = clean_reasoning_tokens(raw)
    text = re.sub(r"```(?:json)?", "", text, flags=re.IGNORECASE).strip()
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except Exception:
        pass
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        try:
            data = json.loads(text[start:end + 1])
            return data if isinstance(data, dict) else None
        except Exception:
            return None
    return None


def no_conversation_result() -> Dict[str, Any]:
    return {
        "intent": "unknown", "lead_label": "no_conversation", "confidence": 1.0,
        "evidence_quote": "", "ai_summary": "Call ended without a meaningful conversation.",
        "needs_human": False, "sentiment": "NEUTRAL", "followup_days": None,
        "model_name": "rules", "review_reasons": [], "keyword_hints": [],
    }


def review_result(reason: str, hints: Optional[Set[str]] = None) -> Dict[str, Any]:
    return {
        "intent": "unknown", "lead_label": "needs_review", "confidence": 0.0,
        "evidence_quote": "",
        "ai_summary": f"Automatic analysis could not classify this call ({reason}); agent review needed.",
        "needs_human": False, "sentiment": "NEUTRAL", "followup_days": None,
        "model_name": None, "review_reasons": [reason], "keyword_hints": sorted(hints or []),
    }


def validate_analysis(
    data: Any,
    caller_lines: List[str],
    intents: List[str],
    labels: List[str],
    hints: Optional[Set[str]] = None,
) -> Dict[str, Any]:
    """Check the LLM answer against the allowed sets and the transcript. Never guesses a label."""
    hints = hints or set()
    if not isinstance(data, dict):
        return review_result("invalid_json", hints)

    reasons: List[str] = []
    intent = str(data.get("intent", "")).strip().lower()
    label = str(data.get("lead_label", "")).strip().lower()

    if intent not in intents:
        reasons.append(f"intent_not_allowed:{intent or 'empty'}")
        intent = "unknown"
    if label not in labels:
        reasons.append(f"label_not_allowed:{label or 'empty'}")
        label = "needs_review"

    try:
        confidence = float(data.get("confidence"))
    except (TypeError, ValueError):
        confidence = 0.0
        reasons.append("confidence_missing")
    confidence = max(0.0, min(1.0, confidence))

    quote = str(data.get("evidence_quote") or "").strip()
    quote_valid = bool(quote) and quote_in_caller_speech(quote, caller_lines)

    if label not in MANDATORY_LABELS:
        if not quote:
            reasons.append("missing_evidence")
        elif not quote_valid:
            reasons.append("evidence_not_in_transcript")
        if confidence < CONFIDENCE_MIN:
            reasons.append("low_confidence")
        if "do_not_call" in hints and label not in ("do_not_call", "not_interested"):
            reasons.append("keyword_hint_conflict:do_not_call")

    if reasons:
        label = "needs_review"

    sentiment = str(data.get("sentiment", "NEUTRAL")).strip().upper()
    if sentiment not in SENTIMENTS:
        sentiment = "NEUTRAL"

    followup_days: Optional[int] = None
    fd = data.get("followup_days")
    if fd is not None:
        try:
            followup_days = max(0, min(90, int(fd)))
        except (TypeError, ValueError):
            followup_days = None
    if label == "callback" and followup_days is None:
        followup_days = 1

    return {
        "intent": intent,
        "lead_label": label,
        "confidence": confidence,
        "evidence_quote": quote if quote_valid else "",
        "ai_summary": str(data.get("ai_summary") or "").strip()[:500],
        "needs_human": bool(data.get("needs_human")),
        "sentiment": sentiment,
        "followup_days": followup_days,
        "model_name": None,
        "review_reasons": reasons,
        "keyword_hints": sorted(hints),
    }


def apply_label_to_contact(contact: Any, label: str) -> Optional[str]:
    """Update ``contact.status`` from a lead label. Returns the new status or None if unchanged.

    * do-not-call / wrong-number / opt-out is sticky: only an explicit agent action clears it.
    * converted customers (any status outside the lead funnel) are never downgraded.
    """
    new_status = LABEL_TO_CONTACT_STATUS.get(label)
    if contact is None or not new_status:
        return None
    current = (getattr(contact, "status", "") or "").upper()
    if current in DO_NOT_CALL_STATUSES and new_status not in DO_NOT_CALL_STATUSES:
        return None
    if new_status in DO_NOT_CALL_STATUSES or current in LEAD_STATUSES:
        if current != new_status:
            contact.status = new_status
            return new_status
    return None


async def classify_transcript(
    transcript: Any,
    intents: List[str],
    labels: List[str],
    org_name: str = "the business",
    industry: str = "",
    llm_call: Optional[LlmCall] = None,
) -> Tuple[Dict[str, Any], str]:
    """Pure classification (no DB). Returns (result, status) where status is DONE or FAILED."""
    if is_short_call(transcript):
        return no_conversation_result(), "DONE"

    lines = caller_turns(transcript)
    hints = keyword_hints(" ".join(lines))
    messages = build_messages(transcript, intents, labels, org_name, industry, hints)

    llm_call = llm_call or groq_json_completion
    raw, model = await llm_call(messages)
    if raw is None:
        return review_result("llm_unavailable", hints), "FAILED"

    data = parse_llm_json(raw)
    if data is None:
        result = review_result("invalid_json", hints)
        result["model_name"] = model
        return result, "FAILED"

    result = validate_analysis(data, lines, intents, labels, hints)
    result["model_name"] = model
    return result, "DONE"


# --------------------------------------------------------------------------------------
# LLM transport (Groq)
# --------------------------------------------------------------------------------------

async def groq_json_completion(messages: List[Dict[str, str]]) -> Tuple[Optional[str], Optional[str]]:
    """Returns (raw_text, model_used) or (None, None) when no model answered."""
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        logger.error("GROQ_API_KEY is not set - call analysis cannot run")
        return None, None
    import httpx  # lazy: keeps the pure helpers importable without network deps

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=25.0) as client:
        for model in LLM_MODELS:
            try:
                resp = await client.post(GROQ_URL, headers=headers, json={
                    "model": model,
                    "messages": messages,
                    "temperature": 0.0,
                    "max_tokens": 600,
                    "response_format": {"type": "json_object"},
                })
                if resp.status_code == 200:
                    return resp.json()["choices"][0]["message"]["content"], model
                logger.warning("Analysis model %s returned HTTP %s: %s", model, resp.status_code, resp.text[:200])
            except Exception as ex:
                logger.warning("Analysis model %s failed: %s", model, ex)
    return None, None


# --------------------------------------------------------------------------------------
# Database layer
# --------------------------------------------------------------------------------------

def _label_config(db, org_id: Optional[str]) -> Tuple[List[str], List[str], str, str]:
    from services.dashboard.app.models.crm import AgentConfig, Organization

    intents, labels = list(DEFAULT_INTENTS), list(DEFAULT_LEAD_LABELS)
    org_name, industry = "the business", ""
    if org_id:
        cfg = db.query(AgentConfig).filter(AgentConfig.organization_id == org_id).first()
        org = db.query(Organization).filter(Organization.id == org_id).first()
        if cfg and cfg.allowed_intents:
            intents = [str(i).lower() for i in cfg.allowed_intents]
        if cfg and cfg.allowed_lead_labels:
            labels = [str(l).lower() for l in cfg.allowed_lead_labels]
        if org:
            org_name, industry = org.name or org_name, org.industry or ""
    if "unknown" not in intents:
        intents.append("unknown")
    for mandatory in MANDATORY_LABELS:
        if mandatory not in labels:
            labels.append(mandatory)
    return intents, labels, org_name, industry


def pick_agent_round_robin(db, org_id: str):
    """Least-loaded active AGENT (ties -> oldest). Increments the counter. Never creates fake agents."""
    from sqlalchemy import func
    from services.dashboard.app.models.crm import TeamMember

    # The UI creates agents with free-text roles such as "Sales Agent", so select by EXCLUSION:
    # anyone active who is not an admin/owner/manager/viewer can receive leads.
    agent = (
        db.query(TeamMember)
        .filter(
            TeamMember.organization_id == org_id,
            TeamMember.is_active == True,  # noqa: E712
            ~func.upper(func.coalesce(TeamMember.role, "AGENT")).in_(list(NON_AGENT_ROLES)),
        )
        .order_by(TeamMember.assigned_leads_count.asc(), TeamMember.created_at.asc())
        .first()
    )
    if agent:
        agent.assigned_leads_count = (agent.assigned_leads_count or 0) + 1
    return agent


def _claim(db, call_session_id: str, force: bool) -> bool:
    """Atomically move a session to RUNNING. False if it is DONE/LEGACY/already running."""
    from sqlalchemy import and_, or_
    from services.dashboard.app.models.crm import CallSession

    now = datetime.utcnow()
    stale = now - timedelta(minutes=STALE_RUNNING_MINUTES)
    q = db.query(CallSession).filter(CallSession.id == call_session_id)
    if not force:
        q = q.filter(or_(
            CallSession.analysis_status.is_(None),
            CallSession.analysis_status.in_(["PENDING", "FAILED"]),
            and_(CallSession.analysis_status == "RUNNING", CallSession.updated_at < stale),
        ))
    changed = q.update({"analysis_status": "RUNNING", "updated_at": now}, synchronize_session=False)
    db.commit()
    return changed == 1


def _persist_interaction(db, session, result: Dict[str, Any]):
    from services.dashboard.app.models.crm import CallInteraction

    interaction = (
        db.query(CallInteraction)
        .filter(CallInteraction.call_id == session.id)
        .order_by(CallInteraction.created_at.desc())
        .first()
    )
    if interaction is None:
        interaction = CallInteraction(
            call_id=session.id,
            organization_id=session.organization_id,
            contact_id=session.contact_id,
        )
        db.add(interaction)

    label = result["lead_label"]
    followup_days = result.get("followup_days")
    interaction.intent_detected = result["intent"]
    interaction.lead_label = label
    interaction.confidence = result["confidence"]
    interaction.evidence_quote = result["evidence_quote"]
    interaction.ai_summary = result["ai_summary"]
    interaction.sentiment = result["sentiment"]
    interaction.model_name = result.get("model_name")
    interaction.prompt_version = PROMPT_VERSION
    interaction.human_handoff_requested = bool(result["needs_human"]) or bool(getattr(session, "handoff_reason", None))
    interaction.followup_required = (label in TASK_LABELS) or (
        followup_days is not None and label not in NO_TASK_LABELS
    )
    interaction.followup_date = (
        datetime.utcnow() + timedelta(days=followup_days) if followup_days is not None else None
    )
    interaction.custom_fields = {
        "review_reasons": result.get("review_reasons", []),
        "keyword_hints": result.get("keyword_hints", []),
    }
    return interaction


def _create_followup_task(db, session, contact, result: Dict[str, Any]):
    """Follow-up LeadTask + LeadReminder for hot/warm/callback leads (idempotent per call)."""
    from services.dashboard.app.models.crm import LeadReminder, LeadTask

    label = result["lead_label"]
    followup_days = result.get("followup_days")
    if label in NO_TASK_LABELS:
        return None
    if not (label in TASK_LABELS or followup_days is not None):
        return None

    marker = f"[call:{session.id}]"
    existing = db.query(LeadTask).filter(LeadTask.description.like(f"%{marker}%")).first()
    if existing:
        return existing

    org_id = session.organization_id
    owner_id = contact.lead_owner_id if contact is not None else None
    if not owner_id and contact is not None:
        agent = pick_agent_round_robin(db, org_id)
        if agent:
            contact.lead_owner_id = agent.id
            owner_id = agent.id

    now = datetime.utcnow()
    if followup_days is not None:
        due = now + timedelta(days=followup_days) if followup_days > 0 else now + timedelta(hours=1)
    else:
        due = now + timedelta(hours=1) if label == "hot" else now + timedelta(days=1)

    name = (contact.name if contact is not None and contact.name else None) or session.from_number
    task = LeadTask(
        id=str(uuid.uuid4()),
        organization_id=org_id,
        contact_id=contact.id if contact is not None else None,
        assigned_to_id=owner_id,
        title=f"{label.upper()} lead - follow up with {name}",
        description=(
            f"{result['ai_summary']}\nCaller said: \"{result['evidence_quote']}\"\n{marker}"
        ),
        status="pending",
        due_at=due,
        custom_inquiry_data={
            "call_id": session.id, "intent": result["intent"],
            "lead_label": label, "sentiment": result["sentiment"],
        },
    )
    db.add(task)
    db.flush()
    db.add(LeadReminder(
        id=str(uuid.uuid4()),
        organization_id=org_id,
        contact_id=contact.id if contact is not None else None,
        task_id=task.id,
        note=f"Follow up ({label}) with {name}: {result['ai_summary']}"[:250],
        remind_at=max(now + timedelta(minutes=5), due - timedelta(minutes=15)),
    ))
    return task


async def analyze_call(
    db,
    call_session_id: str,
    transcript: Optional[list] = None,
    org_id: Optional[str] = None,
    llm_call: Optional[LlmCall] = None,
    force: bool = False,
) -> Dict[str, Any]:
    """Analyse one finished call and write the result into the CRM.

    Safe to call twice (atomic claim), never overwrites an agent's manual correction
    unless ``force=True``, and never raises.
    """
    from services.dashboard.app.models.crm import CallInteraction, CallSession, Contact

    try:
        session = db.query(CallSession).filter(CallSession.id == call_session_id).first()
        if session is None:
            logger.warning("analyze_call: call %s not found", call_session_id)
            return {"skipped": True, "reason": "call_not_found"}

        if not _claim(db, call_session_id, force):
            db.refresh(session)
            return {"skipped": True, "reason": f"status_{session.analysis_status}"}
        db.refresh(session)

        if not force:
            corrected = (
                db.query(CallInteraction)
                .filter(CallInteraction.call_id == session.id, CallInteraction.is_agent_corrected == True)  # noqa: E712
                .first()
            )
            if corrected:
                session.analysis_status = "DONE"
                db.commit()
                return {"skipped": True, "reason": "agent_corrected"}

        if transcript is not None and not session.transcript:
            session.transcript = transcript
        transcript = transcript if transcript is not None else (session.transcript or [])
        org_id = org_id or session.organization_id

        intents, labels, org_name, industry = _label_config(db, org_id)
        result, status = await classify_transcript(transcript, intents, labels, org_name, industry, llm_call)

        _persist_interaction(db, session, result)
        contact = (
            db.query(Contact).filter(Contact.id == session.contact_id).first() if session.contact_id else None
        )
        new_status = apply_label_to_contact(contact, result["lead_label"])
        # A do-not-call / wrong-number contact must never receive a sales follow-up task.
        contact_blocked = contact is not None and (contact.status or "").upper() in DO_NOT_CALL_STATUSES
        task = None
        if status == "DONE" and not contact_blocked:
            task = _create_followup_task(db, session, contact, result)
        if result["ai_summary"] and not session.ai_summary:
            session.ai_summary = result["ai_summary"]
        session.analysis_status = status
        db.commit()

        logger.info(
            "CALL_ANALYSIS call_id=%s status=%s intent=%s label=%s conf=%.2f model=%s contact_status=%s task=%s reasons=%s",
            session.id, status, result["intent"], result["lead_label"], result["confidence"],
            result.get("model_name"), new_status, bool(task), result.get("review_reasons"),
        )
        out = dict(result)
        out.update({"skipped": False, "analysis_status": status, "contact_status": new_status,
                    "task_id": task.id if task else None})
        return out
    except Exception as ex:
        db.rollback()
        logger.exception("analyze_call failed for %s: %s", call_session_id, ex)
        try:
            from services.dashboard.app.models.crm import CallSession as _CS
            db.query(_CS).filter(_CS.id == call_session_id).update(
                {"analysis_status": "FAILED"}, synchronize_session=False
            )
            db.commit()
        except Exception:
            db.rollback()
        return {"skipped": False, "analysis_status": "FAILED", "error": str(ex), "lead_label": "needs_review"}


# --------------------------------------------------------------------------------------
# Background execution + crash recovery
# --------------------------------------------------------------------------------------

_background_tasks: Set[Any] = set()


async def run_call_analysis_in_background(
    call_id: str,
    transcript: Optional[list] = None,
    org_id: Optional[str] = None,
    llm_call: Optional[LlmCall] = None,
) -> Dict[str, Any]:
    """Open a private DB session, analyse, close. Suitable for fire-and-forget."""
    from services.dashboard.app.database import SessionLocal

    db = SessionLocal()
    try:
        return await analyze_call(db, call_id, transcript=transcript, org_id=org_id, llm_call=llm_call)
    finally:
        db.close()


def schedule_call_analysis(call_id: str, transcript: Optional[list] = None, org_id: Optional[str] = None):
    """Fire-and-forget entry point for every gateway / campaign runner when a call ends.

    Works from async code (creates a task) and from plain threads (spawns a daemon thread).
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is not None:
        task = loop.create_task(run_call_analysis_in_background(call_id, transcript, org_id))
        _background_tasks.add(task)  # keep a strong reference so it is not garbage-collected
        task.add_done_callback(_background_tasks.discard)
        return task

    thread = threading.Thread(
        target=lambda: asyncio.run(run_call_analysis_in_background(call_id, transcript, org_id)),
        daemon=True,
        name=f"call-analysis-{call_id[:8]}",
    )
    thread.start()
    return thread


async def retry_pending_analyses(limit: int = 50, max_age_days: int = 7, min_age_s: int = 45) -> int:
    """On startup: finish analyses that were lost to a restart (PENDING / FAILED / stale RUNNING)."""
    from sqlalchemy import and_, or_
    from services.dashboard.app.database import SessionLocal
    from services.dashboard.app.models.crm import CallSession

    now = datetime.utcnow()
    db = SessionLocal()
    try:
        rows = (
            db.query(CallSession.id)
            .filter(
                CallSession.ended_at.isnot(None),
                CallSession.ended_at >= now - timedelta(days=max_age_days),
                CallSession.ended_at <= now - timedelta(seconds=min_age_s),
                or_(
                    CallSession.analysis_status.is_(None),
                    CallSession.analysis_status.in_(["PENDING", "FAILED"]),
                    and_(
                        CallSession.analysis_status == "RUNNING",
                        CallSession.updated_at < now - timedelta(minutes=STALE_RUNNING_MINUTES),
                    ),
                ),
            )
            .order_by(CallSession.ended_at.desc())
            .limit(limit)
            .all()
        )
        ids = [r[0] for r in rows]
    finally:
        db.close()

    done = 0
    for call_id in ids:
        result = await run_call_analysis_in_background(call_id)
        if not result.get("skipped"):
            done += 1
        await asyncio.sleep(0.5)  # be gentle with the LLM rate limit
    if ids:
        logger.info("Call-analysis retry: %d/%d pending calls processed", done, len(ids))
    return done
