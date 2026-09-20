"""
Tests for the unified intent & lead labelling engine.

Run from the product folder:   python -m pytest tests/test_call_analysis.py -v

No network is used (the LLM is faked) and every DB test runs against a temporary SQLite
file, never against voice_crm.db.
"""
import asyncio
import json
import os
import sys
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.dashboard.app.services import call_analysis as ca  # noqa: E402

GOOD_TRANSCRIPT = [
    {"role": "assistant", "content": "Namaste, Smile Dental mein aapka swagat hai."},
    {"role": "user", "content": "Hello, mujhe root canal ka price batao."},
    {"role": "assistant", "content": "Root canal ka charge 4500 rupaye se shuru hota hai."},
    {"role": "user", "content": "Theek hai, kal shaam ko appointment book kar do."},
]

HOT_PAYLOAD = {
    "intent": "site_visit",
    "lead_label": "hot",
    "confidence": 0.93,
    "evidence_quote": "kal shaam ko appointment book kar do",
    "ai_summary": "Caller wants an appointment tomorrow evening.",
    "needs_human": False,
    "sentiment": "POSITIVE",
    "followup_days": None,
}


def fake_llm(payload, calls=None, model="fake-model"):
    async def _llm(messages):
        if calls is not None:
            calls.append(messages)
        raw = payload if isinstance(payload, str) else json.dumps(payload)
        return raw, model
    return _llm


async def unavailable_llm(messages):
    return None, None


async def must_not_be_called(messages):
    raise AssertionError("LLM must not be called in this scenario")


# ----------------------------------------------------------------------------------------
# Pure logic
# ----------------------------------------------------------------------------------------

def test_short_call_detection():
    assert ca.is_short_call([])
    assert ca.is_short_call([{"role": "assistant", "content": "Hello, how can I help you today?"}])
    one_turn = [
        {"role": "assistant", "content": "Namaste, welcome to Smile Dental, how may I help you?"},
        {"role": "user", "content": "Hello?"},
    ]
    assert ca.is_short_call(one_turn)
    assert not ca.is_short_call(GOOD_TRANSCRIPT)


def test_keyword_hints_english_hinglish_and_devanagari():
    assert "do_not_call" in ca.keyword_hints("please don't call me again")
    assert "do_not_call" in ca.keyword_hints("mujhe call mat karna")
    assert "do_not_call" in ca.keyword_hints("\u092e\u0941\u091d\u0947 \u0915\u0949\u0932 \u092e\u0924 \u0915\u0930\u0928\u093e")
    assert "human_transfer" in ca.keyword_hints("I want to talk to a manager")
    assert "human_transfer" in ca.keyword_hints("kisi insaan se baat karwao")
    assert ca.keyword_hints("root canal ka price kya hai") == set()


def test_parse_llm_json_handles_think_tags_and_fences():
    raw = '<think>maybe {not json} here</think>\n```json\n{"a": 1}\n```'
    assert ca.parse_llm_json(raw) == {"a": 1}
    assert ca.parse_llm_json('Sure! Here it is: {"a": 2} hope it helps') == {"a": 2}
    assert ca.parse_llm_json("<think>still thinking, never finished") is None
    assert ca.parse_llm_json("no json at all") is None
    assert ca.parse_llm_json("[1, 2, 3]") is None
    assert ca.parse_llm_json(None) is None


LINES = ["Hello, mujhe root canal ka price batao.", "Theek hai, kal shaam ko appointment book kar do."]
INTENTS = ca.DEFAULT_INTENTS
LABELS = ca.DEFAULT_LEAD_LABELS


def test_quote_matching_ignores_case_and_punctuation():
    assert ca.quote_in_caller_speech("Kal shaam ko, appointment book kar do!", LINES)
    assert not ca.quote_in_caller_speech("I would like to book a visit", LINES)
    assert not ca.quote_in_caller_speech("", LINES)
    assert not ca.quote_in_caller_speech("a", LINES)


def test_validate_accepts_good_answer():
    r = ca.validate_analysis(dict(HOT_PAYLOAD), LINES, INTENTS, LABELS)
    assert r["lead_label"] == "hot"
    assert r["intent"] == "site_visit"
    assert r["evidence_quote"] == "kal shaam ko appointment book kar do"
    assert r["review_reasons"] == []


def test_validate_rejects_invented_quote():
    bad = dict(HOT_PAYLOAD, evidence_quote="I definitely want to buy the premium package")
    r = ca.validate_analysis(bad, LINES, INTENTS, LABELS)
    assert r["lead_label"] == "needs_review"
    assert "evidence_not_in_transcript" in r["review_reasons"]
    assert r["evidence_quote"] == ""


def test_validate_rejects_disallowed_label_or_intent():
    r = ca.validate_analysis(dict(HOT_PAYLOAD, lead_label="super_hot"), LINES, INTENTS, LABELS)
    assert r["lead_label"] == "needs_review"
    r = ca.validate_analysis(dict(HOT_PAYLOAD, intent="banana"), LINES, INTENTS, LABELS)
    assert r["lead_label"] == "needs_review"
    assert r["intent"] == "unknown"


def test_validate_low_confidence_and_missing_evidence():
    assert ca.validate_analysis(dict(HOT_PAYLOAD, confidence=0.2), LINES, INTENTS, LABELS)["lead_label"] == "needs_review"
    assert ca.validate_analysis(dict(HOT_PAYLOAD, evidence_quote=""), LINES, INTENTS, LABELS)["lead_label"] == "needs_review"
    assert ca.validate_analysis(dict(HOT_PAYLOAD, confidence="high"), LINES, INTENTS, LABELS)["lead_label"] == "needs_review"


def test_do_not_call_hint_conflict_goes_to_review():
    r = ca.validate_analysis(dict(HOT_PAYLOAD), LINES, INTENTS, LABELS, hints={"do_not_call"})
    assert r["lead_label"] == "needs_review"
    assert "keyword_hint_conflict:do_not_call" in r["review_reasons"]


def test_validate_normalises_optional_fields():
    r = ca.validate_analysis(dict(HOT_PAYLOAD, sentiment="ecstatic", followup_days=500), LINES, INTENTS, LABELS)
    assert r["sentiment"] == "NEUTRAL"
    assert r["followup_days"] == 90
    cb = dict(HOT_PAYLOAD, lead_label="callback", followup_days=None)
    assert ca.validate_analysis(cb, LINES, INTENTS, LABELS)["followup_days"] == 1


def test_apply_label_to_contact_rules():
    c = SimpleNamespace(status="lead")
    assert ca.apply_label_to_contact(c, "hot") == "HOT_LEAD" and c.status == "HOT_LEAD"

    dnc = SimpleNamespace(status="DO_NOT_CALL")
    assert ca.apply_label_to_contact(dnc, "warm") is None and dnc.status == "DO_NOT_CALL"

    customer = SimpleNamespace(status="customer")
    assert ca.apply_label_to_contact(customer, "cold") is None and customer.status == "customer"
    assert ca.apply_label_to_contact(customer, "do_not_call") == "DO_NOT_CALL"

    assert ca.apply_label_to_contact(SimpleNamespace(status="lead"), "needs_review") is None
    assert ca.apply_label_to_contact(SimpleNamespace(status="lead"), "no_conversation") is None
    assert ca.apply_label_to_contact(None, "hot") is None


def test_prompt_contains_only_allowed_labels_and_roles():
    msgs = ca.build_messages(GOOD_TRANSCRIPT, ["price_query", "unknown"], ["hot", "needs_review"], "Smile Dental", "Dental")
    system, user = msgs[0]["content"], msgs[1]["content"]
    assert '"hot"' in system and "Smile Dental" in system
    assert "- warm:" not in system  # criteria only for allowed labels
    assert "CALLER: Hello, mujhe root canal ka price batao." in user
    assert "ASSISTANT: Namaste" in user


def test_classify_transcript_short_call_never_calls_llm():
    result, status = asyncio.run(
        ca.classify_transcript([], INTENTS, LABELS, llm_call=must_not_be_called)
    )
    assert status == "DONE" and result["lead_label"] == "no_conversation"


def test_classify_transcript_failure_modes():
    result, status = asyncio.run(ca.classify_transcript(GOOD_TRANSCRIPT, INTENTS, LABELS, llm_call=unavailable_llm))
    assert status == "FAILED" and result["lead_label"] == "needs_review"
    result, status = asyncio.run(ca.classify_transcript(GOOD_TRANSCRIPT, INTENTS, LABELS, llm_call=fake_llm("not json")))
    assert status == "FAILED" and result["lead_label"] == "needs_review"


# ----------------------------------------------------------------------------------------
# Database flow (temporary SQLite)
# ----------------------------------------------------------------------------------------

@pytest.fixture()
def env(tmp_path):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from services.dashboard.app.database import Base
    import services.dashboard.app.models  # noqa: F401  (registers every table)

    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    db = Session()
    yield SimpleNamespace(db=db, Session=Session)
    db.close()
    engine.dispose()


def seed(db, call_id="call1", contact_id="c1", contact_status="lead", transcript=None, n_agents=2, first=True):
    from services.dashboard.app.models.crm import CallSession, Contact, Organization, TeamMember

    if first:
        db.add(Organization(id="org1", name="Smile Dental", slug="smile", industry="Dental"))
        for i in range(n_agents):
            db.add(TeamMember(id=f"a{i}", organization_id="org1", name=f"Agent {i}", role="AGENT"))
        db.commit()
    db.add(Contact(id=contact_id, organization_id="org1", phone_number=f"+91{contact_id}", name="Ravi", status=contact_status))
    db.add(CallSession(
        id=call_id, organization_id="org1", contact_id=contact_id,
        from_number="+911111", to_number="+912222",
        transcript=GOOD_TRANSCRIPT if transcript is None else transcript,
        ended_at=datetime.utcnow(),
    ))
    db.commit()


def run(db, call_id="call1", **kw):
    return asyncio.run(ca.analyze_call(db, call_id, **kw))


def get(db, model, **filters):
    return db.query(model).filter_by(**filters).all()


def test_db_short_call_is_labelled_without_llm(env):
    from services.dashboard.app.models.crm import CallInteraction, CallSession, Contact, LeadTask
    seed(env.db, transcript=[{"role": "assistant", "content": "Hello?"}])
    r = run(env.db, llm_call=must_not_be_called)
    assert r["lead_label"] == "no_conversation"
    assert env.db.get(CallSession, "call1").analysis_status == "DONE"
    assert len(get(env.db, CallInteraction, call_id="call1")) == 1
    assert env.db.get(Contact, "c1").status == "lead"
    assert get(env.db, LeadTask) == []


def test_db_hot_lead_updates_contact_and_creates_task_and_owner(env):
    from services.dashboard.app.models.crm import CallInteraction, Contact, LeadReminder, LeadTask
    seed(env.db)
    r = run(env.db, llm_call=fake_llm(HOT_PAYLOAD))
    assert r["lead_label"] == "hot" and r["analysis_status"] == "DONE"

    contact = env.db.get(Contact, "c1")
    assert contact.status == "HOT_LEAD"
    assert contact.lead_owner_id in ("a0", "a1")

    inter = get(env.db, CallInteraction, call_id="call1")[0]
    assert inter.lead_label == "hot" and inter.intent_detected == "site_visit"
    assert inter.evidence_quote == "kal shaam ko appointment book kar do"
    assert inter.model_name == "fake-model" and inter.prompt_version == ca.PROMPT_VERSION
    assert inter.followup_required is True

    tasks = get(env.db, LeadTask)
    assert len(tasks) == 1 and tasks[0].assigned_to_id == contact.lead_owner_id
    assert "[call:call1]" in tasks[0].description
    assert len(get(env.db, LeadReminder)) == 1


def test_db_round_robin_spreads_leads_across_agents(env):
    from services.dashboard.app.models.crm import Contact
    seed(env.db)
    seed(env.db, call_id="call2", contact_id="c2", first=False)
    run(env.db, "call1", llm_call=fake_llm(HOT_PAYLOAD))
    run(env.db, "call2", llm_call=fake_llm(HOT_PAYLOAD))
    owners = {env.db.get(Contact, "c1").lead_owner_id, env.db.get(Contact, "c2").lead_owner_id}
    assert owners == {"a0", "a1"}


def test_db_round_robin_accepts_ui_roles_and_skips_managers(env):
    from services.dashboard.app.models.crm import Contact, TeamMember
    seed(env.db, n_agents=0)
    env.db.add_all([
        TeamMember(id="m1", organization_id="org1", name="Boss", role="MANAGER", assigned_leads_count=0),
        TeamMember(id="s1", organization_id="org1", name="Sales", role="Sales Agent", assigned_leads_count=5),
        TeamMember(id="s2", organization_id="org1", name="Gone", role="Sales Agent", assigned_leads_count=0, is_active=False),
    ])
    env.db.commit()
    run(env.db, llm_call=fake_llm(HOT_PAYLOAD))
    # The manager (lowest count) and the inactive agent are skipped; the UI-created "Sales Agent" gets the lead.
    assert env.db.get(Contact, "c1").lead_owner_id == "s1"


def test_db_existing_owner_is_kept(env):
    from services.dashboard.app.models.crm import Contact, LeadTask
    seed(env.db)
    env.db.get(Contact, "c1").lead_owner_id = "a1"
    env.db.commit()
    run(env.db, llm_call=fake_llm(HOT_PAYLOAD))
    assert get(env.db, LeadTask)[0].assigned_to_id == "a1"


def test_db_invented_quote_goes_to_review_and_changes_nothing(env):
    from services.dashboard.app.models.crm import CallSession, Contact, LeadTask
    seed(env.db)
    bad = dict(HOT_PAYLOAD, evidence_quote="I want the premium package right now")
    r = run(env.db, llm_call=fake_llm(bad))
    assert r["lead_label"] == "needs_review"
    assert env.db.get(CallSession, "call1").analysis_status == "DONE"
    assert env.db.get(Contact, "c1").status == "lead"
    assert get(env.db, LeadTask) == []


def test_db_failed_analysis_is_retryable_and_never_duplicates(env):
    from services.dashboard.app.models.crm import CallInteraction, CallSession, Contact
    seed(env.db)
    r = run(env.db, llm_call=unavailable_llm)
    assert r["analysis_status"] == "FAILED"
    assert env.db.get(CallSession, "call1").analysis_status == "FAILED"

    r = run(env.db, llm_call=fake_llm(HOT_PAYLOAD))
    assert r["analysis_status"] == "DONE"
    assert len(get(env.db, CallInteraction, call_id="call1")) == 1  # updated in place
    assert env.db.get(Contact, "c1").status == "HOT_LEAD"


def test_db_analysis_is_idempotent(env):
    from services.dashboard.app.models.crm import LeadTask
    seed(env.db)
    calls = []
    run(env.db, llm_call=fake_llm(HOT_PAYLOAD, calls))
    again = run(env.db, llm_call=fake_llm(HOT_PAYLOAD, calls))
    assert again["skipped"] is True
    assert len(calls) == 1
    assert len(get(env.db, LeadTask)) == 1


def test_db_do_not_call_is_sticky_and_gets_no_task(env):
    from services.dashboard.app.models.crm import Contact, LeadTask
    seed(env.db, contact_status="DO_NOT_CALL")
    warm = dict(HOT_PAYLOAD, lead_label="warm")
    run(env.db, llm_call=fake_llm(warm))
    assert env.db.get(Contact, "c1").status == "DO_NOT_CALL"
    assert get(env.db, LeadTask) == []


def test_db_customer_says_stop_calling_sets_do_not_call(env):
    from services.dashboard.app.models.crm import Contact, LeadTask
    transcript = [
        {"role": "assistant", "content": "Namaste, Smile Dental se bol rahi hoon, aap kaise hain aaj?"},
        {"role": "user", "content": "Mujhe interest nahi hai."},
        {"role": "assistant", "content": "Koi baat nahi, kya main aapko dobara call kar sakti hoon?"},
        {"role": "user", "content": "Please do not call me again."},
    ]
    seed(env.db, transcript=transcript)
    payload = {
        "intent": "unknown", "lead_label": "do_not_call", "confidence": 0.97,
        "evidence_quote": "Please do not call me again.", "ai_summary": "Caller asked to stop calls.",
        "needs_human": False, "sentiment": "NEGATIVE", "followup_days": None,
    }
    r = run(env.db, llm_call=fake_llm(payload))
    assert r["lead_label"] == "do_not_call"
    assert env.db.get(Contact, "c1").status == "DO_NOT_CALL"
    assert get(env.db, LeadTask) == []


def test_db_agent_correction_is_never_overwritten(env):
    from services.dashboard.app.models.crm import CallInteraction, CallSession
    seed(env.db)
    env.db.add(CallInteraction(
        call_id="call1", organization_id="org1", contact_id="c1",
        lead_label="cold", is_agent_corrected=True, corrected_by_user_id="a0",
    ))
    env.db.commit()
    r = run(env.db, llm_call=must_not_be_called)
    assert r["skipped"] is True and r["reason"] == "agent_corrected"
    assert get(env.db, CallInteraction, call_id="call1")[0].lead_label == "cold"
    assert env.db.get(CallSession, "call1").analysis_status == "DONE"


def test_db_claim_rules_running_legacy_and_force(env):
    from services.dashboard.app.models.crm import CallSession
    seed(env.db)
    sess = env.db.get(CallSession, "call1")

    sess.analysis_status, sess.updated_at = "RUNNING", datetime.utcnow()
    env.db.commit()
    assert run(env.db, llm_call=must_not_be_called)["skipped"] is True  # fresh RUNNING = in progress elsewhere

    sess.analysis_status, sess.updated_at = "RUNNING", datetime.utcnow() - timedelta(minutes=30)
    env.db.commit()
    assert run(env.db, llm_call=fake_llm(HOT_PAYLOAD))["analysis_status"] == "DONE"  # stale RUNNING = crashed

    sess.analysis_status = "LEGACY"
    env.db.commit()
    assert run(env.db, llm_call=must_not_be_called)["skipped"] is True
    assert run(env.db, llm_call=fake_llm(HOT_PAYLOAD), force=True)["skipped"] is False


def test_db_per_organization_label_set_is_enforced(env):
    from services.dashboard.app.models.crm import AgentConfig
    seed(env.db)
    env.db.add(AgentConfig(organization_id="org1", allowed_lead_labels=["hot", "cold"]))
    env.db.commit()
    r = run(env.db, llm_call=fake_llm(dict(HOT_PAYLOAD, lead_label="warm")))
    assert r["lead_label"] == "needs_review"
    assert any(x.startswith("label_not_allowed") for x in r["review_reasons"])


def test_db_transcript_argument_is_stored_when_session_has_none(env):
    from services.dashboard.app.models.crm import CallSession
    seed(env.db, transcript=[])
    run(env.db, transcript=GOOD_TRANSCRIPT, llm_call=fake_llm(HOT_PAYLOAD))
    assert env.db.get(CallSession, "call1").transcript == GOOD_TRANSCRIPT


def test_retry_pending_analyses_only_touches_eligible_calls(env, monkeypatch):
    from services.dashboard.app import database
    from services.dashboard.app.models.crm import CallSession

    seed(env.db)                                                  # call1: eligible (PENDING, ended long ago)
    seed(env.db, call_id="call2", contact_id="c2", first=False)   # call2: LEGACY
    seed(env.db, call_id="call3", contact_id="c3", first=False)   # call3: ended just now
    seed(env.db, call_id="call4", contact_id="c4", first=False)   # call4: older than the retry window
    now = datetime.utcnow()
    env.db.get(CallSession, "call1").ended_at = now - timedelta(minutes=5)
    env.db.get(CallSession, "call2").ended_at = now - timedelta(minutes=5)
    env.db.get(CallSession, "call2").analysis_status = "LEGACY"
    env.db.get(CallSession, "call3").ended_at = now
    env.db.get(CallSession, "call4").ended_at = now - timedelta(days=30)
    env.db.commit()

    monkeypatch.setattr(database, "SessionLocal", env.Session)
    monkeypatch.setattr(ca, "groq_json_completion", fake_llm(HOT_PAYLOAD))

    processed = asyncio.run(ca.retry_pending_analyses())
    assert processed == 1

    env.db.expire_all()
    status = {c: env.db.get(CallSession, c).analysis_status for c in ("call1", "call2", "call3", "call4")}
    assert status == {"call1": "DONE", "call2": "LEGACY", "call3": "PENDING", "call4": "PENDING"}
