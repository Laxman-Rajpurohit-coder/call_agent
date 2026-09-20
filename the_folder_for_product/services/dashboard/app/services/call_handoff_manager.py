import time
import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import text, update

from services.dashboard.app.models.crm import TeamMember, CallSession, CallHandoffAttempt, Contact, LeadTask
from services.dashboard.app.services.agent_presence_service import AgentPresenceService

logger = logging.getLogger("CallHandoffManager")

# ------------------------------------------------------------------------------
# TELEPHONY ADAPTER ABSTRACTION
# ------------------------------------------------------------------------------
class BaseTelephonyAdapter:
    def bridge_call(self, call_session: CallSession, agent: TeamMember) -> bool:
        raise NotImplementedError

    def cancel_ringing(self, call_session: CallSession, agent: TeamMember) -> bool:
        raise NotImplementedError

    def supervisor_action(self, call_session: CallSession, supervisor_id: str, action: str) -> Dict[str, Any]:
        raise NotImplementedError

class TwilioAdapter(BaseTelephonyAdapter):
    def bridge_call(self, call_session: CallSession, agent: TeamMember) -> bool:
        logger.info("[TwilioAdapter] Bridging call %s to agent %s (%s)", call_session.id, agent.name, agent.phone)
        return True

    def cancel_ringing(self, call_session: CallSession, agent: TeamMember) -> bool:
        logger.info("[TwilioAdapter] Cancelled leg for agent %s", agent.id)
        return True

    def supervisor_action(self, call_session: CallSession, supervisor_id: str, action: str) -> Dict[str, Any]:
        logger.info("[TwilioAdapter] Supervisor %s requested %s on call %s", supervisor_id, action, call_session.id)
        return {"status": "success", "action": action, "channel": f"twilio_sup_{call_session.id}"}

class ExotelAdapter(BaseTelephonyAdapter):
    def bridge_call(self, call_session: CallSession, agent: TeamMember) -> bool:
        logger.info("[ExotelAdapter] Bridging Exotel call %s to agent %s (%s)", call_session.id, agent.name, agent.phone)
        return True

    def cancel_ringing(self, call_session: CallSession, agent: TeamMember) -> bool:
        logger.info("[ExotelAdapter] Cancelled Exotel leg for agent %s", agent.id)
        return True

    def supervisor_action(self, call_session: CallSession, supervisor_id: str, action: str) -> Dict[str, Any]:
        logger.info("[ExotelAdapter] Supervisor %s action %s on Exotel call %s", supervisor_id, action, call_session.id)
        return {"status": "success", "action": action, "channel": f"exotel_sup_{call_session.id}"}

class AsteriskAdapter(BaseTelephonyAdapter):
    def bridge_call(self, call_session: CallSession, agent: TeamMember) -> bool:
        logger.info("[AsteriskAdapter] PJSIP dial to extension %s for call %s", agent.sip_extension, call_session.id)
        return True

    def cancel_ringing(self, call_session: CallSession, agent: TeamMember) -> bool:
        return True

    def supervisor_action(self, call_session: CallSession, supervisor_id: str, action: str) -> Dict[str, Any]:
        # ChanSpy options: LISTEN = q, WHISPER = w, BARGE = B
        spy_flags = {"LISTEN": "q", "WHISPER": "w", "BARGE": "B"}.get(action, "q")
        logger.info("[AsteriskAdapter] ChanSpy(%s,%s) triggered for supervisor %s on call %s", agent_ext := getattr(call_session.handled_by, 'sip_extension', '100'), spy_flags, supervisor_id, call_session.id)
        return {"status": "success", "action": action, "spy_flags": spy_flags}

class WebRTCAdapter(BaseTelephonyAdapter):
    def bridge_call(self, call_session: CallSession, agent: TeamMember) -> bool:
        logger.info("[WebRTCAdapter] WebRTC media socket bridge established for call %s with agent %s", call_session.id, agent.id)
        return True

    def cancel_ringing(self, call_session: CallSession, agent: TeamMember) -> bool:
        return True

    def supervisor_action(self, call_session: CallSession, supervisor_id: str, action: str) -> Dict[str, Any]:
        return {"status": "success", "action": action, "webrtc_stream": f"sup_stream_{call_session.id}"}

class TelephonyProviderFactory:
    _adapters = {
        "twilio": TwilioAdapter(),
        "exotel": ExotelAdapter(),
        "asterisk": AsteriskAdapter(),
        "audiosocket": AsteriskAdapter(),
        "webrtc": WebRTCAdapter(),
        "app": WebRTCAdapter(),
    }

    @classmethod
    def get_adapter(cls, provider_name: str) -> BaseTelephonyAdapter:
        p = (provider_name or "webrtc").lower()
        return cls._adapters.get(p, WebRTCAdapter())


# ------------------------------------------------------------------------------
# CALL HANDOFF MANAGER
# ------------------------------------------------------------------------------
class CallHandoffManager:
    @staticmethod
    def initiate_handoff(
        db: Session,
        call_session_id: str,
        reason: str = "CUSTOMER_REQUESTED_HUMAN",
        ai_summary: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        organization_id: str = "default-org"
    ) -> Dict[str, Any]:
        """Initiates parallel ringing handoff to available & healthy agent pool."""
        call_session = db.query(CallSession).filter(CallSession.id == call_session_id).first()
        if not call_session:
            return {"error": "Call session not found", "status": "failed"}

        # Idempotency Check
        if idempotency_key and call_session.idempotency_key == idempotency_key:
            logger.info("Duplicate initiate_handoff call with key %s -> returning existing state %s", idempotency_key, call_session.handoff_status)
            return {
                "status": call_session.handoff_status,
                "call_id": call_session.id,
                "message": "Duplicate request processed idempotently"
            }

        if call_session.customer_disconnected:
            return {"status": "cancelled", "reason": "CALLER_HUNG_UP"}

        # Query Available Agents
        available_agents = AgentPresenceService.get_available_agents(db, organization_id=organization_id)
        if not available_agents:
            logger.warning("No AVAILABLE agents found for handoff of call %s -> Executing Fallback", call_session_id)
            call_session.handoff_status = "FAILED_NO_AGENTS"
            call_session.handoff_failure_reason = "NO_AVAILABLE_AGENTS"
            db.commit()
            CallHandoffManager._trigger_fallback_task(db, call_session, "NO_AVAILABLE_AGENTS")
            return {"status": "failed", "reason": "NO_AVAILABLE_AGENTS"}

        now = datetime.utcnow()
        call_session.handoff_status = "WAITING_FOR_AGENT"
        call_session.handoff_reason = reason
        call_session.ai_summary = ai_summary or "Customer requested human support."
        call_session.idempotency_key = idempotency_key

        offered_agent_ids = []
        for agent in available_agents:
            agent.presence_status = "RINGING"
            offered_agent_ids.append(agent.id)

            attempt = CallHandoffAttempt(
                call_session_id=call_session.id,
                agent_id=agent.id,
                offered_at=now,
                ring_started_at=now,
                result="OFFERED"
            )
            db.add(attempt)

        db.commit()
        logger.info("Initiated parallel handoff for call %s across %d agents (%s)", call_session.id, len(offered_agent_ids), offered_agent_ids)

        return {
            "status": "WAITING_FOR_AGENT",
            "call_id": call_session.id,
            "offered_agents_count": len(offered_agent_ids),
            "offered_agent_ids": offered_agent_ids,
            "reason": reason,
            "ai_summary": call_session.ai_summary
        }

    @staticmethod
    def atomic_accept_call(
        db: Session,
        call_session_id: str,
        agent_id: str,
        idempotency_key: Optional[str] = None
    ) -> Dict[str, Any]:
        """Atomically claims call ownership for the first answering agent."""
        now = datetime.utcnow()
        call_session = db.query(CallSession).filter(CallSession.id == call_session_id).first()
        if not call_session:
            return {"error": "Call session not found", "status": "failed"}

        # Idempotency Check for double clicks from same agent
        if call_session.handled_by_user_id == agent_id and call_session.handoff_status in ["AGENT_ACCEPTED", "BRIDGING", "HUMAN_CONNECTED"]:
            logger.info("Agent %s idempotent double-accept on call %s -> Returning current state %s", agent_id, call_session_id, call_session.handoff_status)
            return {"status": "success", "handoff_status": call_session.handoff_status, "agent_id": agent_id}

        if call_session.customer_disconnected:
            return {"status": "cancelled", "reason": "CALLER_HUNG_UP", "message": "Customer hung up before call was answered"}

        # ⚡ ATOMIC SQL UPDATE
        result = db.execute(
            text("""
                UPDATE call_sessions 
                SET handled_by_user_id = :agent_id,
                    handoff_status = 'AGENT_ACCEPTED',
                    accepted_at = :accepted_at
                WHERE id = :call_session_id 
                  AND handoff_status = 'WAITING_FOR_AGENT'
            """),
            {"agent_id": agent_id, "accepted_at": now, "call_session_id": call_session_id}
        )
        db.commit()

        # Check if update succeeded (Winner) or failed (Lost race)
        if result.rowcount == 0:
            logger.warning("Agent %s lost race to claim call %s (already claimed by another agent)", agent_id, call_session_id)
            return {
                "status": "already_accepted",
                "message": "Call was answered by another agent",
                "winner_agent_id": call_session.handled_by_user_id
            }

        # 🏆 WINNING AGENT LOGIC
        winning_agent = db.query(TeamMember).filter(TeamMember.id == agent_id).first()
        if winning_agent:
            winning_agent.presence_status = "BUSY"
            winning_agent.current_call_id = call_session.id

        # Update winning attempt log
        winning_attempt = db.query(CallHandoffAttempt).filter(
            CallHandoffAttempt.call_session_id == call_session_id,
            CallHandoffAttempt.agent_id == agent_id
        ).first()
        if winning_attempt:
            winning_attempt.answered_at = now
            winning_attempt.result = "ANSWERED"

        # Release losing agents back to AVAILABLE
        losing_attempts = db.query(CallHandoffAttempt).filter(
            CallHandoffAttempt.call_session_id == call_session_id,
            CallHandoffAttempt.agent_id != agent_id
        ).all()

        for att in losing_attempts:
            att.cancelled_at = now
            att.result = "CANCELLED_OTHER_WON"
            other_agent = db.query(TeamMember).filter(TeamMember.id == att.agent_id).first()
            if other_agent and other_agent.presence_status == "RINGING":
                other_agent.presence_status = "AVAILABLE"

        db.commit()
        db.refresh(call_session)

        # 📞 TELEPHONY BRIDGING STAGE
        call_session.handoff_status = "BRIDGING"
        call_session.bridge_started_at = datetime.utcnow()
        db.commit()

        adapter = TelephonyProviderFactory.get_adapter(call_session.provider)
        bridge_success = adapter.bridge_call(call_session, winning_agent)

        if bridge_success:
            call_session.handoff_status = "HUMAN_CONNECTED"
            call_session.human_connected_at = datetime.utcnow()
            call_session.status = "in_progress"
            db.commit()
            logger.info("✅ Call %s successfully bridged to agent %s (%s) -> Status HUMAN_CONNECTED", call_session.id, winning_agent.name, agent_id)
            return {
                "status": "success",
                "handoff_status": "HUMAN_CONNECTED",
                "agent_id": agent_id,
                "agent_name": winning_agent.name,
                "call_id": call_session.id
            }
        else:
            # 🔴 TELEPHONY BRIDGE FAILURE RECOVERY
            logger.error("❌ Telephony bridge failed for call %s to agent %s -> Rolling back agent presence", call_session.id, agent_id)
            call_session.handoff_status = "BRIDGE_FAILED"
            call_session.handoff_failure_reason = "BRIDGE_FAILURE"
            if winning_agent:
                winning_agent.presence_status = "AVAILABLE"
                winning_agent.current_call_id = None
            db.commit()

            CallHandoffManager._trigger_fallback_task(db, call_session, "BRIDGE_FAILURE")
            return {"status": "failed", "reason": "BRIDGE_FAILURE", "message": "Telephony audio bridge setup failed"}

    @staticmethod
    def reject_call(db: Session, call_session_id: str, agent_id: str) -> Dict[str, Any]:
        """Records agent rejection and releases agent back to AVAILABLE."""
        now = datetime.utcnow()
        attempt = db.query(CallHandoffAttempt).filter(
            CallHandoffAttempt.call_session_id == call_session_id,
            CallHandoffAttempt.agent_id == agent_id
        ).first()

        if attempt:
            attempt.rejected_at = now
            attempt.result = "REJECTED"

        agent = db.query(TeamMember).filter(TeamMember.id == agent_id).first()
        if agent and agent.presence_status == "RINGING":
            agent.presence_status = "AVAILABLE"

        db.commit()

        # Check if all offered agents rejected
        remaining = db.query(CallHandoffAttempt).filter(
            CallHandoffAttempt.call_session_id == call_session_id,
            CallHandoffAttempt.result == "OFFERED"
        ).count()

        if remaining == 0:
            call_session = db.query(CallSession).filter(CallSession.id == call_session_id).first()
            if call_session and call_session.handoff_status == "WAITING_FOR_AGENT":
                call_session.handoff_status = "REJECTED"
                call_session.handoff_failure_reason = "ALL_AGENTS_REJECTED"
                db.commit()
                CallHandoffManager._trigger_fallback_task(db, call_session, "ALL_AGENTS_REJECTED")

        return {"status": "rejected", "agent_id": agent_id, "remaining_ringing": remaining}

    @staticmethod
    def handle_customer_hangup(db: Session, call_session_id: str) -> Dict[str, Any]:
        """Cancels all ringing legs and releases agents when customer disconnects."""
        call_session = db.query(CallSession).filter(CallSession.id == call_session_id).first()
        if not call_session:
            return {"error": "Call session not found"}

        now = datetime.utcnow()
        call_session.customer_disconnected = True
        call_session.handoff_status = "CANCELLED"
        call_session.handoff_failure_reason = "CALLER_HUNG_UP"

        # Cancel all offered legs
        attempts = db.query(CallHandoffAttempt).filter(
            CallHandoffAttempt.call_session_id == call_session_id,
            CallHandoffAttempt.result.in_(["OFFERED", "ANSWERED"])
        ).all()

        for att in attempts:
            att.cancelled_at = now
            att.result = "CALLER_HUNG_UP"
            ag = db.query(TeamMember).filter(TeamMember.id == att.agent_id).first()
            if ag and ag.presence_status in ["RINGING", "BUSY"] and ag.current_call_id == call_session_id:
                ag.presence_status = "AVAILABLE"
                ag.current_call_id = None

        db.commit()
        logger.info("Customer hung up during handoff of call %s -> Released all agents", call_session_id)
        return {"status": "cancelled", "reason": "CALLER_HUNG_UP"}

    @staticmethod
    def supervisor_action(db: Session, call_session_id: str, supervisor_id: str, action: str) -> Dict[str, Any]:
        """Executes LISTEN, WHISPER, BARGE, or STOP on an active human call."""
        valid_actions = {"LISTEN", "WHISPER", "BARGE", "STOP"}
        if action not in valid_actions:
            return {"error": f"Invalid supervisor action: {action}. Valid: {valid_actions}"}

        call_session = db.query(CallSession).filter(CallSession.id == call_session_id).first()
        if not call_session:
            return {"error": "Call session not found"}

        adapter = TelephonyProviderFactory.get_adapter(call_session.provider)
        res = adapter.supervisor_action(call_session, supervisor_id, action)
        logger.info("Supervisor %s executed %s on call %s -> %s", supervisor_id, action, call_session_id, res)
        return res

    @staticmethod
    def _trigger_fallback_task(db: Session, call_session: CallSession, failure_reason: str):
        """Creates a high-priority CRM lead task when human handoff cannot be fulfilled."""
        try:
            task = LeadTask(
                organization_id=call_session.organization_id,
                contact_id=call_session.contact_id,
                title=f"🚨 URGENT: Failed Call Handoff ({failure_reason})",
                description=f"Call from {call_session.from_number} required human handoff but failed. Reason: {failure_reason}. AI Summary: {call_session.ai_summary}",
                status="pending",
                due_at=datetime.utcnow() + timedelta(minutes=15)
            )
            db.add(task)
            db.commit()
            logger.info("Created urgent CRM task %s for failed handoff (%s)", task.id, failure_reason)
        except Exception as ex:
            logger.error("Failed to create fallback task: %s", ex)
