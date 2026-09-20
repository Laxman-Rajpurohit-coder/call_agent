import time
import asyncio
from datetime import datetime
from typing import Dict, Any, Optional, Set

class CallRegistry:
    """
    Authoritative In-Memory Registry for Live Telephony Sessions.
    Guarantees:
    1. Monotonically increasing sequence per call ID (Constraint 3)
    2. Heartbeat tracking for live media/telephony health (Constraint 2)
    3. Active telephony dialog verification for reconciler (Constraint 1 & 2)
    4. Safe programmatic termination (Constraint 1)
    """

    def __init__(self):
        self._active_sessions: Dict[str, Dict[str, Any]] = {}
        self._call_sequences: Dict[str, int] = {}
        self._lock = asyncio.Lock()

    def get_next_sequence(self, call_id: str) -> int:
        """Returns a strictly monotonically increasing sequence number per call_id."""
        if not call_id:
            return 0
        seq = self._call_sequences.get(call_id, 0) + 1
        self._call_sequences[call_id] = seq
        return seq

    def get_current_sequence(self, call_id: str) -> int:
        return self._call_sequences.get(call_id, 0)

    def register_call(
        self,
        call_id: str,
        caller=None,
        rtp_sock=None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Registers a live call session into memory."""
        now = datetime.utcnow()
        session_entry = {
            "call_id": call_id,
            "caller": caller,
            "rtp_sock": rtp_sock,
            "started_at": now,
            "last_heartbeat_at": now,
            "media_status": "RECEIVING",
            "vad_state": "LISTENING",
            "metadata": metadata or {},
            "is_terminated": False
        }
        self._active_sessions[call_id] = session_entry
        if call_id not in self._call_sequences:
            self._call_sequences[call_id] = 0
        return session_entry

    def record_heartbeat(
        self,
        call_id: str,
        media_status: Optional[str] = None,
        vad_state: Optional[str] = None
    ):
        """Updates telephony & media heartbeat for an active session."""
        sess = self._active_sessions.get(call_id)
        if sess:
            sess["last_heartbeat_at"] = datetime.utcnow()
            if media_status:
                sess["media_status"] = media_status
            if vad_state:
                sess["vad_state"] = vad_state

    def get_call_heartbeat(self, call_id: str) -> Optional[datetime]:
        sess = self._active_sessions.get(call_id)
        return sess.get("last_heartbeat_at") if sess else None

    def get_session(self, call_id: str) -> Optional[Dict[str, Any]]:
        return self._active_sessions.get(call_id)

    def is_call_active(self, call_id: str) -> bool:
        """
        Authoritatively checks whether a call is genuinely active in the telephony engine.
        Returns False if the session does not exist, was marked terminated,
        or caller SIP dialog has ended.
        """
        sess = self._active_sessions.get(call_id)
        if not sess or sess.get("is_terminated"):
            return False

        caller = sess.get("caller")
        if caller:
            # Check if caller instance indicates answered state
            if hasattr(caller, "is_answered") and not caller.is_answered:
                return False
            # Check if socket is open
            if hasattr(caller, "sip_sock"):
                try:
                    caller.sip_sock.getsockname()
                except Exception:
                    return False

        # Verify that heartbeat is not ancient (> 45s without any media packet)
        last_hb = sess.get("last_heartbeat_at")
        if last_hb and (datetime.utcnow() - last_hb).total_seconds() > 45:
            return False

        return True

    def get_active_call_ids(self) -> Set[str]:
        return set(self._active_sessions.keys())

    async def terminate_call(self, call_id: str) -> bool:
        """Terminates active telephony session, sending SIP BYE and closing sockets."""
        sess = self._active_sessions.get(call_id)
        if not sess:
            return False

        sess["is_terminated"] = True
        caller = sess.get("caller")
        if caller:
            if hasattr(caller, "is_answered"):
                caller.is_answered = False
            if hasattr(caller, "send_bye"):
                try:
                    await caller.send_bye()
                except Exception:
                    pass

        rtp_sock = sess.get("rtp_sock")
        if rtp_sock:
            try:
                rtp_sock.close()
            except Exception:
                pass

        self._active_sessions.pop(call_id, None)
        return True

    def unregister_call(self, call_id: str):
        self._active_sessions.pop(call_id, None)


# Global singleton instance
call_registry = CallRegistry()
