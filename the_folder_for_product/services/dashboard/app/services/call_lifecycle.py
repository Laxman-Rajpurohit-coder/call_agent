"""
Call lifecycle - the ONE place where the voice gateway writes calls into the CRM database.

    start_call(...)      when the caller is connected   -> organization + contact + CallSession
    heartbeat_call(...)  every few seconds during a call -> keeps the dashboard reaper from ending it
    end_call(...)        when the call ends              -> transcript, duration, recording, then analysis

Why heartbeats matter: the dashboard reaper (call_reconciler.py) asks an IN-MEMORY registry inside
the dashboard process whether a call is alive.  The gateway is a different process, so that registry
never knows its calls.  The only thing that keeps a live call from being marked "completed" after
~45 seconds is a fresh ``last_heartbeat_at`` in the database - so the gateway must send heartbeats.

Every function here is safe to call from the gateway: it never raises, and the ``a*`` variants run
the (blocking) database work in a worker thread so the audio loop is never stalled.

Only stdlib is imported at module level; models / database are imported lazily so the pure helpers
(phone normalisation, recording lookup, transcript cleaning) can be unit-tested on their own.
"""

import asyncio
import glob
import logging
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("call_lifecycle")

# Caller-ID values that carry no identity (no contact is created for these)
ANONYMOUS_CALLER_IDS = {"", "unknown", "<unknown>", "anonymous", "restricted", "private", "unavailable", "none", "null"}


# --------------------------------------------------------------------------------------
# Pure helpers
# --------------------------------------------------------------------------------------

def _default_cc() -> str:
    return os.environ.get("DEFAULT_COUNTRY_CODE", "91")


def is_real_caller(value: Any) -> bool:
    return value is not None and str(value).strip().lower() not in ANONYMOUS_CALLER_IDS


def normalize_phone(raw: Any, default_cc: Optional[str] = None) -> Optional[str]:
    """Normalise a phone number to E.164 (+919876543210).

    * SIP usernames / anything containing letters (e.g. "test1000") are returned unchanged.
    * Short internal extensions (e.g. "700") are returned as plain digits.
    """
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    if re.search(r"[A-Za-z]", s):
        return s
    cc = default_cc or _default_cc()
    digits = re.sub(r"\D", "", s)
    if not digits:
        return None
    if s.startswith("+"):
        return "+" + digits
    if digits.startswith("00") and len(digits) > 4:
        return "+" + digits[2:]
    if digits.startswith("0") and len(digits) == 11:            # 09876543210
        return "+" + cc + digits[1:]
    if len(digits) == 10:                                        # 9876543210
        return "+" + cc + digits
    if digits.startswith(cc) and len(digits) == len(cc) + 10:    # 919876543210
        return "+" + digits
    if len(digits) >= 11:
        return "+" + digits
    return digits                                                # internal extension


def phone_variants(e164: Optional[str], default_cc: Optional[str] = None) -> Set[str]:
    """Every way the same number may already be stored (so we never create duplicate contacts)."""
    if not e164:
        return set()
    cc = default_cc or _default_cc()
    variants = {e164, e164.lstrip("+")}
    digits = e164.lstrip("+")
    if e164.startswith("+") and digits.startswith(cc) and len(digits) == len(cc) + 10:
        national = digits[len(cc):]
        variants.update({national, "0" + national, cc + national, "+" + cc + national})
    return variants


def map_handoff_reason(text: Optional[str]) -> str:
    """Map the gateway's free-text reason to the CRM's handoff_reason vocabulary."""
    t = (text or "").lower()
    if "pressed 0" in t or "keypad" in t or "manager" in t or "human" in t or "person" in t:
        return "CUSTOMER_REQUESTED_HUMAN"
    if "confidence" in t or "sensitive" in t:
        return "AI_LOW_CONFIDENCE"
    return "AI_OUT_OF_SCOPE"


def clean_transcript(history: Any) -> List[Dict[str, str]]:
    """Keep only well-formed {role, content} turns."""
    out: List[Dict[str, str]] = []
    for turn in history or []:
        if not isinstance(turn, dict):
            continue
        role = str(turn.get("role", "")).strip().lower()
        content = str(turn.get("content") or turn.get("text") or "").strip()
        if role in ("user", "assistant", "system") and content:
            out.append({"role": role, "content": content})
    return out


def find_recording(call_id: str, recordings_dir: Optional[str] = None) -> Optional[str]:
    """Asterisk names recordings '<call_id>-<timestamp>.wav' (see extensions_local.conf MixMonitor).

    Returns the file name (not the full path) of the newest match, or None.
    """
    base = recordings_dir
    if base is None:
        try:
            from services.dashboard.app.config import settings
            base = settings.RECORDINGS_DIR
        except Exception:
            return None
    if not base or not os.path.isdir(base):
        return None
    safe = re.sub(r"[^0-9a-fA-F\-]", "", str(call_id or ""))  # uuid characters only -> no glob injection
    if not safe:
        return None
    matches = glob.glob(os.path.join(glob.escape(base), f"{safe}*.wav"))
    if not matches:
        return None
    return os.path.basename(max(matches, key=os.path.getmtime))


# --------------------------------------------------------------------------------------
# Database operations (blocking)
# --------------------------------------------------------------------------------------

def resolve_organization(db, to_number: Optional[str] = None) -> Tuple[Any, str]:
    """Which business does this call belong to?  Returns (organization | None, how_resolved).

    1. The dialed number is registered under an organization (Organization -> Phone Numbers)
    2. DEFAULT_ORGANIZATION_SLUG in .env
    3. Exactly one active organization exists
    4. Otherwise the oldest organization (with a warning - register your numbers to fix this)
    """
    from services.dashboard.app.models.crm import Organization, PhoneNumber

    if to_number and is_real_caller(to_number):
        variants = phone_variants(normalize_phone(to_number))
        if variants:
            pn = (
                db.query(PhoneNumber)
                .filter(PhoneNumber.phone_number.in_(list(variants)))
                .order_by(PhoneNumber.created_at.asc())
                .first()
            )
            if pn:
                org = db.query(Organization).filter(Organization.id == pn.organization_id).first()
                if org:
                    return org, "phone_number"

    slug = os.environ.get("DEFAULT_ORGANIZATION_SLUG", "").strip()
    if slug:
        org = db.query(Organization).filter(Organization.slug == slug).first()
        if org:
            return org, "default_slug"

    orgs = (
        db.query(Organization)
        .filter(Organization.is_active == True)  # noqa: E712
        .order_by(Organization.created_at.asc())
        .all()
    )
    if len(orgs) == 1:
        return orgs[0], "single_org"
    if orgs:
        logger.warning(
            "Cannot tell which organization owns dialed number %r - using '%s'. "
            "Register the number under the organization's phone numbers.", to_number, orgs[0].slug,
        )
        return orgs[0], "fallback_first"
    return None, "none"


def find_or_create_contact(db, org_id: str, phone: Any, source: str = "Inbound Call"):
    from services.dashboard.app.models.crm import Contact

    if not is_real_caller(phone):
        return None
    e164 = normalize_phone(phone)
    if not e164:
        return None
    variants = phone_variants(e164) | {str(phone).strip()}
    contact = (
        db.query(Contact)
        .filter(Contact.organization_id == org_id, Contact.phone_number.in_(list(variants)))
        .first()
    )
    if contact:
        return contact
    contact = Contact(
        organization_id=org_id, phone_number=e164, status="lead",
        lead_source=source, preferred_language="hi",
    )
    db.add(contact)
    db.flush()
    return contact


def start_call(
    call_id: str,
    from_number: Optional[str],
    to_number: Optional[str],
    direction: str = "inbound",
    provider: str = "vobiz",
) -> Dict[str, Any]:
    """Create (or return) the CallSession for a connected call. Returns {} if the CRM is unreachable."""
    from services.dashboard.app.database import SessionLocal
    from services.dashboard.app.models.crm import CallSession

    db = SessionLocal()
    try:
        existing = db.query(CallSession).filter(CallSession.id == call_id).first()
        if existing:
            from services.dashboard.app.models.crm import Organization
            existing_org = db.query(Organization).filter(Organization.id == existing.organization_id).first() if existing.organization_id else None
            return {
                "call_id": call_id,
                "organization_id": existing.organization_id,
                "organization_slug": existing_org.slug if existing_org else None,
                "contact_id": existing.contact_id,
                "resolved_by": "existing_session",
                "existing": True,
            }

        inbound = direction != "outbound"
        org, how = resolve_organization(db, to_number if inbound else from_number)
        if org is None:
            logger.error("start_call: no organization exists in the CRM - call %s will not be recorded", call_id)
            return {}

        contact = find_or_create_contact(db, org.id, from_number if inbound else to_number)
        now = datetime.utcnow()
        db.add(CallSession(
            id=call_id,
            organization_id=org.id,
            contact_id=contact.id if contact else None,
            provider=provider,
            direction=direction,
            from_number=str(from_number or "unknown"),
            to_number=str(to_number or "unknown"),
            status="in_progress",
            started_at=now,
            answered_at=now,
            last_heartbeat_at=now,
            media_status="RECEIVING",
            vad_state="LISTENING",
            transcript=[],
            analysis_status="PENDING",
        ))
        if contact is not None:
            contact.last_called_at = now
        db.commit()
        return {
            "call_id": call_id,
            "organization_id": org.id,
            "organization_slug": org.slug,
            "contact_id": contact.id if contact else None,
            "contact_status": contact.status if contact else None,
            "resolved_by": how,
        }
    except Exception as ex:
        db.rollback()
        logger.exception("start_call failed for %s: %s", call_id, ex)
        return {}
    finally:
        db.close()


def heartbeat_call(call_id: str, media_status: str = "RECEIVING", vad_state: Optional[str] = None) -> bool:
    """Prove the call is alive (and revive it if the dashboard reaper flagged it RECOVERY_PENDING)."""
    from services.dashboard.app.database import SessionLocal
    from services.dashboard.app.models.crm import CallSession

    db = SessionLocal()
    try:
        values: Dict[str, Any] = {"last_heartbeat_at": datetime.utcnow(), "media_status": media_status}
        if vad_state:
            values["vad_state"] = vad_state
        changed = db.query(CallSession).filter(CallSession.id == call_id).update(values, synchronize_session=False)
        db.query(CallSession).filter(
            CallSession.id == call_id, CallSession.status == "RECOVERY_PENDING"
        ).update({"status": "in_progress"}, synchronize_session=False)
        db.commit()
        return changed == 1
    except Exception as ex:
        db.rollback()
        logger.warning("heartbeat_call failed for %s: %s", call_id, ex)
        return False
    finally:
        db.close()


def end_call(
    call_id: str,
    transcript_history: Optional[list] = None,
    status: str = "completed",
    handoff_requested: bool = False,
    handoff_reason: Optional[str] = None,
    recordings_dir: Optional[str] = None,
    schedule_analysis: bool = True,
) -> Dict[str, Any]:
    """Finalise the CallSession and queue the post-call analysis."""
    from services.dashboard.app.database import SessionLocal
    from services.dashboard.app.models.crm import CallSession

    db = SessionLocal()
    try:
        session = db.query(CallSession).filter(CallSession.id == call_id).first()
        if session is None:
            logger.warning("end_call: call %s has no CRM session (start_call failed or never ran)", call_id)
            return {"ok": False, "reason": "session_not_found"}

        ended = datetime.utcnow()
        started = session.started_at or session.created_at
        duration = max(round((ended - started).total_seconds(), 1), 0.0) if started else (session.duration_s or 0.0)

        session.status = status
        session.ended_at = ended
        session.duration_s = duration
        session.media_status = "DISCONNECTED"
        session.vad_state = "IDLE"
        if transcript_history is not None:
            session.transcript = clean_transcript(transcript_history)

        if handoff_requested:
            session.handoff_reason = map_handoff_reason(handoff_reason)
            cf = dict(session.custom_fields or {})
            cf["handoff"] = {"requested": True, "reason_text": handoff_reason}
            session.custom_fields = cf

        recording = find_recording(call_id, recordings_dir)
        if recording:
            session.recording_storage_key = recording
            session.recording_url = f"/recordings/{recording}"
        else:
            logger.warning("end_call: no recording file found for %s (is Asterisk's monitor folder mounted "
                           "into the recordings directory?)", call_id)

        # Always (re)analyse with the FINAL transcript, except sessions deliberately excluded.
        if not str(session.analysis_status or "").startswith("SKIPPED"):
            session.analysis_status = "PENDING"
        db.commit()

        if schedule_analysis:
            from services.dashboard.app.services.call_analysis import schedule_call_analysis
            schedule_call_analysis(call_id)
        return {"ok": True, "duration_s": duration, "recording": recording,
                "turns": len(session.transcript or []), "organization_id": session.organization_id}
    except Exception as ex:
        db.rollback()
        logger.exception("end_call failed for %s: %s", call_id, ex)
        return {"ok": False, "reason": str(ex)}
    finally:
        db.close()


# --------------------------------------------------------------------------------------
# Async wrappers for the gateway (DB work runs in a worker thread; never raises)
# --------------------------------------------------------------------------------------

async def astart_call(**kwargs) -> Dict[str, Any]:
    try:
        return await asyncio.to_thread(start_call, **kwargs)
    except Exception as ex:
        logger.error("astart_call failed: %s", ex)
        return {}


async def aheartbeat_call(call_id: str, media_status: str = "RECEIVING", vad_state: Optional[str] = None) -> bool:
    try:
        return await asyncio.to_thread(heartbeat_call, call_id, media_status, vad_state)
    except Exception:
        return False


async def aend_call(**kwargs) -> Dict[str, Any]:
    try:
        result = await asyncio.to_thread(end_call, schedule_analysis=False, **kwargs)
        if result.get("ok"):
            # Scheduled on the running loop (not in the worker thread) so it is a normal background task.
            from services.dashboard.app.services.call_analysis import schedule_call_analysis
            schedule_call_analysis(kwargs["call_id"])
        return result
    except Exception as ex:
        logger.error("aend_call failed: %s", ex)
        return {"ok": False, "reason": str(ex)}
