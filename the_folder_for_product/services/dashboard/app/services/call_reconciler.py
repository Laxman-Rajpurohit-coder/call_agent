import asyncio
import uuid
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from services.dashboard.app.models.crm import CallSession
from services.dashboard.app.services.call_registry import call_registry
from services.dashboard.app.services.event_bus import manager, broadcast_call_event

async def reconcile_active_sessions(db: Session, heartbeat_timeout_seconds: int = 20, recovery_timeout_seconds: int = 25) -> int:
    """
    Heartbeat-based safe reconciler (Constraint 2).
    State Machine:
      CONNECTED -> (no heartbeat for > 20s) -> verify telephony
        ├─ Telephony says active -> CONNECTED (heartbeat refreshed)
        ├─ Telephony says ended -> ENDED
        └─ Telephony unknown -> RECOVERY_PENDING -> (timeout > 25s) -> ENDED
    """
    now = datetime.utcnow()
    hb_cutoff = now - timedelta(seconds=heartbeat_timeout_seconds)
    recovery_cutoff = now - timedelta(seconds=recovery_timeout_seconds)

    # Active states
    active_statuses = ["in_progress", "active", "connected", "initiated", "RINGING", "CONNECTED", "HUMAN_CONNECTED", "RECOVERY_PENDING"]
    candidates = db.query(CallSession).filter(
        CallSession.status.in_(active_statuses)
    ).all()

    reconciled_count = 0

    for sess in candidates:
        call_id = sess.id
        is_active_in_telephony = call_registry.is_call_active(call_id)

        # 1. Telephony verifies call is ALIVE
        if is_active_in_telephony:
            # If it was in RECOVERY_PENDING, recover it!
            if sess.status == "RECOVERY_PENDING":
                sess.status = "connected"
                sess.media_status = "RECEIVING"
                sess.last_heartbeat_at = now
                db.commit()
                if broadcast_call_event:
                    await broadcast_call_event("CALL_STATE_CHANGED", call_id, {
                        "status": "CONNECTED",
                        "media_status": "RECEIVING"
                    })
            else:
                # Refresh heartbeat in DB
                sess.last_heartbeat_at = now
                sess.media_status = "RECEIVING"
            continue

        # 2. Telephony indicates call is NOT active
        last_hb = sess.last_heartbeat_at or sess.started_at or sess.created_at

        # Check if already in RECOVERY_PENDING
        if sess.status == "RECOVERY_PENDING":
            # If in recovery for longer than recovery_timeout_seconds, finalize to ENDED
            if sess.updated_at and sess.updated_at < recovery_cutoff:
                sess.status = "completed"
                sess.ended_at = now
                sess.media_status = "DISCONNECTED"
                if sess.started_at:
                    sess.duration_s = max(round((sess.ended_at - sess.started_at).total_seconds(), 1), sess.duration_s or 0.0)
                db.commit()
                reconciled_count += 1
                if broadcast_call_event:
                    await broadcast_call_event("CALL_ENDED", call_id, {
                        "reason": "RECOVERY_TIMEOUT",
                        "duration_s": sess.duration_s
                    })
                call_registry.unregister_call(call_id)
        else:
            # Transition to RECOVERY_PENDING if no heartbeat past cutoff
            if last_hb and last_hb < hb_cutoff:
                sess.status = "RECOVERY_PENDING"
                sess.media_status = "DEGRADED"
                sess.updated_at = now
                db.commit()
                if broadcast_call_event:
                    await broadcast_call_event("CALL_STATE_CHANGED", call_id, {
                        "status": "RECOVERY_PENDING",
                        "media_status": "DEGRADED",
                        "reason": "HEARTBEAT_MISSING"
                    })

    if reconciled_count > 0:
        db.commit()

    return reconciled_count
