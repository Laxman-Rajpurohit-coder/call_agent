"""
Tests for the gateway <-> CRM boundary (call_lifecycle.py) and the live-monitor log contract.

Run from the product folder:   python -m pytest tests/test_call_lifecycle.py -v

No network, no Asterisk, no real DB: every DB test uses a temporary SQLite file.
"""
import asyncio
import json
import os
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.dashboard.app.services import call_lifecycle as cl  # noqa: E402

CALL_ID = "0a1b2c3d-1111-2222-3333-444455556666"


# ----------------------------------------------------------------------------------------
# Pure helpers
# ----------------------------------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("+919812345678", "+919812345678"),
    ("9812345678", "+919812345678"),
    ("09812345678", "+919812345678"),
    ("919812345678", "+919812345678"),
    ("+91 98123-45678", "+919812345678"),
    ("(+91) 98123 45678", "+919812345678"),
    ("00919812345678", "+919812345678"),
    ("+14155550123", "+14155550123"),
    ("700", "700"),                 # internal extension stays as-is
    ("test1000", "test1000"),       # SIP username stays as-is
    ("", None),
    (None, None),
    ("---", None),
])
def test_normalize_phone(raw, expected):
    assert cl.normalize_phone(raw) == expected


def test_phone_variants_cover_every_stored_format():
    v = cl.phone_variants("+919812345678")
    assert {"+919812345678", "919812345678", "9812345678", "09812345678"} <= v
    assert cl.phone_variants("700") == {"700"}
    assert cl.phone_variants(None) == set()


def test_is_real_caller():
    for bad in (None, "", "  ", "unknown", "<unknown>", "Anonymous", "restricted", "None"):
        assert not cl.is_real_caller(bad), bad
    for good in ("9812345678", "+919812345678", "test1000"):
        assert cl.is_real_caller(good), good


def test_map_handoff_reason():
    assert cl.map_handoff_reason("User pressed 0 on keypad") == "CUSTOMER_REQUESTED_HUMAN"
    assert cl.map_handoff_reason("low confidence / sensitive request") == "AI_LOW_CONFIDENCE"
    assert cl.map_handoff_reason("STT pool at capacity") == "AI_OUT_OF_SCOPE"
    assert cl.map_handoff_reason(None) == "AI_OUT_OF_SCOPE"


def test_clean_transcript_drops_garbage():
    raw = [
        {"role": "assistant", "content": "  Namaste  "},
        {"role": "user", "content": ""},
        {"role": "USER", "text": "price batao"},
        {"role": "tool", "content": "ignored"},
        "not a dict",
        {"content": "no role"},
    ]
    assert cl.clean_transcript(raw) == [
        {"role": "assistant", "content": "Namaste"},
        {"role": "user", "content": "price batao"},
    ]
    assert cl.clean_transcript(None) == []


def test_find_recording_prefers_newest_and_ignores_others(tmp_path):
    (tmp_path / f"{CALL_ID}.wav").write_bytes(b"a")
    newest = tmp_path / f"{CALL_ID}-20260920-101010.wav"
    newest.write_bytes(b"b")
    (tmp_path / "ffffffff-0000-0000-0000-000000000000-20260920.wav").write_bytes(b"c")
    (tmp_path / "ex_call_1789117227.wav").write_bytes(b"d")
    old = time.time() - 3600
    os.utime(tmp_path / f"{CALL_ID}.wav", (old, old))
    assert cl.find_recording(CALL_ID, str(tmp_path)) == newest.name
    assert cl.find_recording("00000000-0000-0000-0000-000000000000", str(tmp_path)) is None
    assert cl.find_recording(CALL_ID, str(tmp_path / "missing")) is None


def test_find_recording_cannot_be_abused_with_glob_characters(tmp_path):
    (tmp_path / "secret.wav").write_bytes(b"x")
    assert cl.find_recording("*", str(tmp_path)) is None
    assert cl.find_recording("../*", str(tmp_path)) is None
    assert cl.find_recording("", str(tmp_path)) is None


# ----------------------------------------------------------------------------------------
# Live-monitor log contract (gateway writes it, event_bus parses it)
# ----------------------------------------------------------------------------------------

def _log(msg):
    return f"2026-09-20 10:00:00,123 - INFO - call_gateway.session - {msg}"


def test_live_monitor_parses_user_and_ai_lines_with_apostrophes():
    from services.dashboard.app.services.event_bus import parse_log_line

    user = parse_log_line(_log("USER_UTTERANCE call_id='abc-123' text='I'm fine, don't call later'"))
    assert user["event_type"] == "TRANSCRIPT_FINAL"
    assert user["call_id"] == "abc-123"
    assert user["payload"] == {"speaker": "USER", "text": "I'm fine, don't call later"}

    ai = parse_log_line(_log("AI_RESPONSE call_id='abc-123' text='Sure, I'll help you with that.'"))
    assert ai["payload"] == {"speaker": "AI", "text": "Sure, I'll help you with that."}


def test_live_monitor_parses_call_start_and_end_with_call_id():
    from services.dashboard.app.services.event_bus import parse_log_line

    started = parse_log_line(_log(f"Call session started with call_id={CALL_ID}"))
    assert started["event_type"] == "CALL_CONNECTED" and started["call_id"] == CALL_ID
    ended = parse_log_line(_log(f"Call session finished. Connection closed. call_id={CALL_ID}"))
    assert ended["event_type"] == "CALL_ENDED" and ended["call_id"] == CALL_ID


def test_record_turn_appends_history_and_logs_parseable_line(caplog):
    from services.call_gateway.session import CallSessionHandler
    from services.dashboard.app.services.event_bus import parse_log_line

    fake = SimpleNamespace(conversation_history=[], session=SimpleNamespace(call_id="abc-123"))
    with caplog.at_level("INFO", logger="call_gateway.session"):
        CallSessionHandler._record_turn(fake, "user", "  hello\nthere  ")
        CallSessionHandler._record_turn(fake, "assistant", "")          # ignored
        CallSessionHandler._record_turn(fake, "assistant", "Namaste ji")
    assert fake.conversation_history == [
        {"role": "user", "content": "hello there"},
        {"role": "assistant", "content": "Namaste ji"},
    ]
    parsed = [parse_log_line(_log(r.getMessage())) for r in caplog.records if "call_id='abc-123'" in r.getMessage()]
    assert [p["payload"]["text"] for p in parsed] == ["hello there", "Namaste ji"]


# ----------------------------------------------------------------------------------------
# Database flow
# ----------------------------------------------------------------------------------------

@pytest.fixture()
def env(tmp_path, monkeypatch):
    from sqlalchemy import create_engine, event
    from sqlalchemy.orm import sessionmaker
    from services.dashboard.app import database
    import services.dashboard.app.models  # noqa: F401  (registers every table)

    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _pragmas(dbapi_conn, _):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA busy_timeout=5000")
        cur.close()

    database.Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    monkeypatch.setattr(database, "SessionLocal", Session)      # what call_lifecycle opens
    monkeypatch.delenv("DEFAULT_ORGANIZATION_SLUG", raising=False)
    monkeypatch.setenv("DEFAULT_COUNTRY_CODE", "91")
    yield SimpleNamespace(Session=Session, recordings=str(tmp_path))
    engine.dispose()


@contextmanager
def fresh(env):
    s = env.Session()
    try:
        yield s
    finally:
        s.close()


def add_org(env, org_id="org1", slug="smile-dental", name="Smile Dental", created=None):
    from services.dashboard.app.models.crm import Organization
    with fresh(env) as s:
        s.add(Organization(id=org_id, name=name, slug=slug, created_at=created or datetime.utcnow()))
        s.commit()


def start(call_id=CALL_ID, caller="09812345678", to="+918065354620", **kw):
    return cl.start_call(call_id, caller, to, **kw)


def test_start_call_creates_session_and_contact(env):
    from services.dashboard.app.models.crm import CallSession, Contact
    add_org(env)
    info = start()
    assert info["organization_id"] == "org1" and info["resolved_by"] == "single_org"

    with fresh(env) as s:
        call = s.get(CallSession, CALL_ID)
        assert call.status == "in_progress" and call.provider == "vobiz" and call.direction == "inbound"
        assert call.from_number == "09812345678" and call.to_number == "+918065354620"
        assert call.analysis_status == "PENDING" and call.media_status == "RECEIVING"
        contact = s.get(Contact, call.contact_id)
        assert contact.phone_number == "+919812345678" and contact.status == "lead"
        assert contact.organization_id == "org1" and contact.last_called_at is not None


def test_same_caller_in_different_formats_is_one_contact(env):
    from services.dashboard.app.models.crm import Contact
    add_org(env)
    start("aaaaaaaa-0000-0000-0000-000000000001", caller="9812345678")
    start("aaaaaaaa-0000-0000-0000-000000000002", caller="+919812345678")
    start("aaaaaaaa-0000-0000-0000-000000000003", caller="919812345678")
    with fresh(env) as s:
        assert s.query(Contact).count() == 1


def test_start_call_is_idempotent(env):
    from services.dashboard.app.models.crm import CallSession
    add_org(env)
    first = start()
    again = start()
    assert again.get("existing") is True and again["contact_id"] == first["contact_id"]
    with fresh(env) as s:
        assert s.query(CallSession).count() == 1


def test_anonymous_caller_creates_call_but_no_contact(env):
    from services.dashboard.app.models.crm import CallSession, Contact
    add_org(env)
    info = start(caller="anonymous")
    assert info["contact_id"] is None
    with fresh(env) as s:
        assert s.get(CallSession, CALL_ID).contact_id is None
        assert s.query(Contact).count() == 0


def test_no_organization_means_no_crash(env):
    assert start() == {}


def test_organization_resolution_order(env, monkeypatch):
    from services.dashboard.app.models.crm import PhoneNumber
    old = datetime.utcnow() - timedelta(days=30)
    add_org(env, "org1", "smile-dental", "Smile Dental", created=old)
    add_org(env, "org2", "navbharat-ngo", "Navbharat NGO")

    # 1. two orgs, number not registered -> oldest org (with a warning)
    assert start("aaaaaaaa-0000-0000-0000-00000000000a")["resolved_by"] == "fallback_first"

    # 2. DEFAULT_ORGANIZATION_SLUG wins over the fallback
    monkeypatch.setenv("DEFAULT_ORGANIZATION_SLUG", "navbharat-ngo")
    info = start("aaaaaaaa-0000-0000-0000-00000000000b")
    assert info["organization_id"] == "org2" and info["resolved_by"] == "default_slug"

    # 3. a registered number wins over everything
    with fresh(env) as s:
        s.add(PhoneNumber(organization_id="org1", phone_number="+918065354620", provider="Vobiz"))
        s.commit()
    info = start("aaaaaaaa-0000-0000-0000-00000000000c", to="08065354620")   # different format, same number
    assert info["organization_id"] == "org1" and info["resolved_by"] == "phone_number"


def test_heartbeat_refreshes_and_revives_recovery_pending(env):
    from services.dashboard.app.models.crm import CallSession
    add_org(env)
    start()
    old = datetime.utcnow() - timedelta(minutes=5)
    with fresh(env) as s:
        call = s.get(CallSession, CALL_ID)
        call.last_heartbeat_at, call.status, call.media_status = old, "RECOVERY_PENDING", "DEGRADED"
        s.commit()

    assert cl.heartbeat_call(CALL_ID, "RECEIVING", "SPEAKING") is True
    with fresh(env) as s:
        call = s.get(CallSession, CALL_ID)
        assert call.status == "in_progress"
        assert call.last_heartbeat_at > old + timedelta(minutes=4)
        assert call.media_status == "RECEIVING" and call.vad_state == "SPEAKING"

    assert cl.heartbeat_call("does-not-exist") is False


TRANSCRIPT = [
    {"role": "assistant", "content": "Namaste, Smile Dental mein aapka swagat hai."},
    {"role": "user", "content": "Hello, mujhe root canal ka price batao."},
    {"role": "assistant", "content": "Root canal ka charge 4500 rupaye se shuru hota hai."},
    {"role": "user", "content": "Theek hai, kal shaam ko appointment book kar do."},
]


def test_end_call_finalises_session(env):
    from services.dashboard.app.models.crm import CallSession
    add_org(env)
    start()
    with fresh(env) as s:   # pretend the call has been running for 42 seconds
        s.get(CallSession, CALL_ID).started_at = datetime.utcnow() - timedelta(seconds=42)
        s.commit()
    rec = f"{CALL_ID}-20260920-101010.wav"
    open(os.path.join(env.recordings, rec), "wb").write(b"RIFF")

    r = cl.end_call(
        CALL_ID, TRANSCRIPT + [{"role": "user", "content": "   "}], handoff_requested=True,
        handoff_reason="User pressed 0 on keypad", recordings_dir=env.recordings, schedule_analysis=False,
    )
    assert r["ok"] is True and r["turns"] == 4 and r["recording"] == rec

    with fresh(env) as s:
        call = s.get(CallSession, CALL_ID)
        assert call.status == "completed" and call.ended_at is not None
        assert 41 <= call.duration_s <= 45
        assert call.media_status == "DISCONNECTED" and call.vad_state == "IDLE"
        assert call.transcript == TRANSCRIPT
        assert call.recording_storage_key == rec and call.recording_url == f"/recordings/{rec}"
        assert call.handoff_reason == "CUSTOMER_REQUESTED_HUMAN"
        assert call.custom_fields["handoff"]["reason_text"] == "User pressed 0 on keypad"
        assert call.analysis_status == "PENDING"


def test_end_call_keeps_skipped_simulated_sessions_excluded(env):
    from services.dashboard.app.models.crm import CallSession
    add_org(env)
    start()
    with fresh(env) as s:
        s.get(CallSession, CALL_ID).analysis_status = "SKIPPED_SIMULATED"
        s.commit()
    cl.end_call(CALL_ID, TRANSCRIPT, recordings_dir=env.recordings, schedule_analysis=False)
    with fresh(env) as s:
        assert s.get(CallSession, CALL_ID).analysis_status == "SKIPPED_SIMULATED"


def test_end_call_without_start_call_does_not_crash(env):
    r = cl.end_call("ffffffff-0000-0000-0000-000000000000", TRANSCRIPT, schedule_analysis=False)
    assert r == {"ok": False, "reason": "session_not_found"}


def test_full_pipeline_start_end_analyse(env):
    """The point of phase 1: a finished call becomes a labelled lead with a follow-up task."""
    from services.dashboard.app.models.crm import CallInteraction, CallSession, Contact, LeadTask, TeamMember
    from services.dashboard.app.services import call_analysis as ca

    add_org(env)
    with fresh(env) as s:
        s.add(TeamMember(id="a1", organization_id="org1", name="Sales Agent 1", role="Sales Agent"))
        s.commit()
    start()
    cl.end_call(
        CALL_ID, TRANSCRIPT, handoff_requested=True, handoff_reason="User pressed 0 on keypad",
        recordings_dir=env.recordings, schedule_analysis=False,
    )

    payload = {
        "intent": "site_visit", "lead_label": "hot", "confidence": 0.93,
        "evidence_quote": "kal shaam ko appointment book kar do",
        "ai_summary": "Wants an appointment tomorrow evening.",
        "needs_human": False, "sentiment": "POSITIVE", "followup_days": None,
    }

    async def llm(messages):
        return json.dumps(payload), "fake-model"

    with fresh(env) as s:
        result = asyncio.run(ca.analyze_call(s, CALL_ID, llm_call=llm))
    assert result["lead_label"] == "hot" and result["analysis_status"] == "DONE"

    with fresh(env) as s:
        contact = s.query(Contact).one()
        assert contact.phone_number == "+919812345678" and contact.status == "HOT_LEAD"
        assert contact.lead_owner_id == "a1"                       # UI-style "Sales Agent" role is eligible
        inter = s.query(CallInteraction).one()
        assert inter.lead_label == "hot"
        assert inter.human_handoff_requested is True               # came from the DTMF-0 handoff, not the LLM
        assert s.get(CallSession, CALL_ID).analysis_status == "DONE"
        task = s.query(LeadTask).one()
        assert task.assigned_to_id == "a1" and task.contact_id == contact.id


def test_transcript_from_a_barge_in_call_keeps_the_interrupting_caller(env):
    """Regression: the interrupted turn (caller cut the AI off) used to vanish from the transcript."""
    from services.dashboard.app.models.crm import CallSession
    add_org(env)
    start()
    history = [
        {"role": "assistant", "content": "Namaste, aapka swagat hai."},
        {"role": "user", "content": "Root canal ka price kya hai?"},
        {"role": "assistant", "content": "Root canal ka charge"},          # interrupted mid-sentence
        {"role": "user", "content": "Nahi nahi, mujhe appointment chahiye."},
        {"role": "assistant", "content": "Ji, kis din ke liye?"},
    ]
    cl.end_call(CALL_ID, history, schedule_analysis=False)
    with fresh(env) as s:
        saved = s.get(CallSession, CALL_ID).transcript
    assert [t["content"] for t in saved if t["role"] == "user"] == [
        "Root canal ka price kya hai?", "Nahi nahi, mujhe appointment chahiye.",
    ]
