import sys
import os
import asyncio
import uuid
from datetime import datetime, timedelta

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

from services.dashboard.app.database import SessionLocal, run_migrations
from services.dashboard.app.models.crm import CallSession, Organization
from services.dashboard.app.services.call_registry import call_registry
from services.dashboard.app.services.call_reconciler import reconcile_active_sessions
from services.dashboard.app.services.event_bus import broadcast_call_event

async def test_all_constraints():
    print("==================================================================")
    print("  AUTOMATED VERIFICATION: 5 LIVE CALL MONITOR ARCHITECTURAL CONSTRAINTS")
    print("==================================================================")

    # 0. Ensure schema migrations applied
    run_migrations()
    db = SessionLocal()

    try:
        # ----------------------------------------------------------------------
        # CONSTRAINT 3: Monotonic Per-Call Sequences
        # ----------------------------------------------------------------------
        print("\n--- [Constraint 3] Testing Monotonic Per-Call Sequence Generation ---")
        call_1 = f"call-seq-{uuid.uuid4().hex[:6]}"
        call_2 = f"call-seq-{uuid.uuid4().hex[:6]}"

        seq1_1 = call_registry.get_next_sequence(call_1)
        seq1_2 = call_registry.get_next_sequence(call_1)
        seq2_1 = call_registry.get_next_sequence(call_2)
        seq1_3 = call_registry.get_next_sequence(call_1)
        seq2_2 = call_registry.get_next_sequence(call_2)

        assert seq1_1 == 1, f"Expected 1, got {seq1_1}"
        assert seq1_2 == 2, f"Expected 2, got {seq1_2}"
        assert seq1_3 == 3, f"Expected 3, got {seq1_3}"
        assert seq2_1 == 1, f"Expected 1 for call 2, got {seq2_1}"
        assert seq2_2 == 2, f"Expected 2 for call 2, got {seq2_2}"
        print(f"✅ Call 1 sequence: {seq1_1}, {seq1_2}, {seq1_3} (Monotonically increasing)")
        print(f"✅ Call 2 sequence: {seq2_1}, {seq2_2} (Strictly isolated per-call sequence)")

        # ----------------------------------------------------------------------
        # CONSTRAINT 1: Authoritative Lifecycle & 4 Independent Dimensions
        # ----------------------------------------------------------------------
        print("\n--- [Constraint 1] Testing 4 Independent Telemetry Dimensions ---")
        test_cid = f"test-call-dims-{uuid.uuid4().hex[:6]}"
        org = db.query(Organization).first()
        org_id = org.id if org else "default-org"

        sess = CallSession(
            id=test_cid,
            organization_id=org_id,
            from_number="+918000000700",
            to_number="+919876543210",
            status="CONNECTED",
            media_status="RECEIVING",
            vad_state="LISTENING",
            last_heartbeat_at=datetime.utcnow(),
            started_at=datetime.utcnow()
        )
        db.add(sess)
        db.commit()

        # Register into telephony registry
        call_registry.register_call(test_cid, caller=None, rtp_sock=None)
        call_registry.record_heartbeat(test_cid, media_status="RECEIVING", vad_state="LISTENING")

        from services.dashboard.app.api.calls import enrich_call_session
        enriched = enrich_call_session(sess)

        assert enriched.status == "CONNECTED", f"Wrong status: {enriched.status}"
        assert enriched.media["rtp"] == "RECEIVING", f"Wrong media: {enriched.media}"
        assert enriched.vad_state == "LISTENING", f"Wrong VAD: {enriched.vad_state}"
        assert enriched.handler["type"] == "AI", f"Wrong handler: {enriched.handler}"
        print(f"✅ Dimension 1 (Call Status): {enriched.status}")
        print(f"✅ Dimension 2 (Media Status): {enriched.media['rtp']} ({enriched.media['codec']})")
        print(f"✅ Dimension 3 (VAD State): {enriched.vad_state}")
        print(f"✅ Dimension 4 (Handler Attribution): {enriched.handler['name']} [{enriched.handler['type']}]")

        # ----------------------------------------------------------------------
        # CONSTRAINT 2: Heartbeat-Based Reconciler (Protects Long Calls)
        # ----------------------------------------------------------------------
        print("\n--- [Constraint 2] Testing Heartbeat Reconciler & Recovery State Machine ---")
        # Scenario A: Legitimate long call (e.g. 10 minutes old) with active heartbeat in call_registry
        long_call_id = f"long-call-{uuid.uuid4().hex[:6]}"
        long_sess = CallSession(
            id=long_call_id,
            organization_id=org_id,
            from_number="+918000000700",
            to_number="+919999999999",
            status="CONNECTED",
            media_status="RECEIVING",
            vad_state="LISTENING",
            created_at=datetime.utcnow() - timedelta(minutes=10), # 10 minutes old!
            started_at=datetime.utcnow() - timedelta(minutes=10),
            last_heartbeat_at=datetime.utcnow() # fresh heartbeat!
        )
        db.add(long_sess)
        db.commit()

        # Register in call_registry
        call_registry.register_call(long_call_id)
        call_registry.record_heartbeat(long_call_id, media_status="RECEIVING")

        # Run reconciler
        reconciled = await reconcile_active_sessions(db, heartbeat_timeout_seconds=20, recovery_timeout_seconds=25)
        db.refresh(long_sess)
        assert long_sess.status == "CONNECTED" or long_sess.status == "connected", f"Long call was killed! Status: {long_sess.status}"
        print(f"✅ Long Call Safety: 10-minute active call was NOT terminated (Status: {long_sess.status})")

        # Scenario B: Stale call with no heartbeat -> Transitions to RECOVERY_PENDING
        stale_call_id = f"stale-call-{uuid.uuid4().hex[:6]}"
        stale_sess = CallSession(
            id=stale_call_id,
            organization_id=org_id,
            from_number="+918000000700",
            to_number="+918888888888",
            status="CONNECTED",
            media_status="RECEIVING",
            created_at=datetime.utcnow() - timedelta(seconds=35),
            started_at=datetime.utcnow() - timedelta(seconds=35),
            last_heartbeat_at=datetime.utcnow() - timedelta(seconds=35) # Dead heartbeat
        )
        db.add(stale_sess)
        db.commit()

        # Reconciler pass 1 -> transitions to RECOVERY_PENDING
        await reconcile_active_sessions(db, heartbeat_timeout_seconds=20, recovery_timeout_seconds=25)
        db.refresh(stale_sess)
        assert stale_sess.status == "RECOVERY_PENDING", f"Expected RECOVERY_PENDING, got {stale_sess.status}"
        assert stale_sess.media_status == "DEGRADED", f"Expected DEGRADED, got {stale_sess.media_status}"
        print(f"✅ Recovery State Machine Pass 1: Missing heartbeat transitioned to RECOVERY_PENDING (Status: {stale_sess.status})")

        # Reconciler pass 2 -> past recovery timeout -> transitions to completed
        stale_sess.updated_at = datetime.utcnow() - timedelta(seconds=30)
        db.commit()
        await reconcile_active_sessions(db, heartbeat_timeout_seconds=20, recovery_timeout_seconds=25)
        db.refresh(stale_sess)
        assert stale_sess.status == "completed", f"Expected completed, got {stale_sess.status}"
        print(f"✅ Recovery State Machine Pass 2: Expired recovery finalized to {stale_sess.status}")

        # ----------------------------------------------------------------------
        # CONSTRAINT 4 & 5: Event Bus Telemetry & Call-Scoped Transcripts
        # ----------------------------------------------------------------------
        print("\n--- [Constraint 4 & 5] Testing Event Envelopes & Call-Scoped Events ---")
        partial_evt = await broadcast_call_event("TRANSCRIPT_PARTIAL", test_cid, {
            "speaker": "USER",
            "text": "Hello this is part",
            "partial": True,
            "turn_id": f"{test_cid}-u-1"
        })
        assert partial_evt["sequence"] > 0, "Missing sequence in envelope"
        assert partial_evt["call_id"] == test_cid, "Mismatched call_id"
        print(f"✅ Partial speech event envelope verified: seq={partial_evt['sequence']}, event_id={partial_evt['event_id']}")

        final_evt = await broadcast_call_event("TRANSCRIPT_FINAL", test_cid, {
            "speaker": "USER",
            "text": "Hello this is partial speech turn finalized",
            "partial": False,
            "turn_id": f"{test_cid}-u-1"
        })
        assert final_evt["sequence"] > partial_evt["sequence"], "Final sequence not strictly greater than partial"
        print(f"✅ Final speech event envelope verified: seq={final_evt['sequence']} > partial seq={partial_evt['sequence']}")

        # ----------------------------------------------------------------------
        # CLEANUP
        # ----------------------------------------------------------------------
        db.query(CallSession).filter(CallSession.id.in_([test_cid, long_call_id, stale_call_id])).delete(synchronize_session=False)
        db.commit()
        call_registry.unregister_call(test_cid)
        call_registry.unregister_call(long_call_id)
        call_registry.unregister_call(stale_call_id)
        print("\n==================================================================")
        print("  ALL 5 ARCHITECTURAL CONSTRAINTS VERIFIED SUCCESSFULLY!")
        print("==================================================================")

    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(test_all_constraints())
