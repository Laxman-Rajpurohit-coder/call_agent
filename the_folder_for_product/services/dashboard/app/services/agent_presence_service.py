import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from services.dashboard.app.models.crm import TeamMember

logger = logging.getLogger("AgentPresenceService")

class AgentPresenceService:
    @staticmethod
    def record_heartbeat(db: Session, agent_id: str, device_status: str = "REGISTERED") -> Dict[str, Any]:
        """Updates agent heartbeat and device reachability status."""
        agent = db.query(TeamMember).filter(TeamMember.id == agent_id).first()
        if not agent:
            return {"error": "Agent not found"}

        now = datetime.utcnow()
        agent.last_heartbeat_at = now
        agent.device_status = device_status
        if agent.presence_status == "OFFLINE":
            agent.presence_status = "AVAILABLE"
            logger.info("Agent %s (%s) presence restored to AVAILABLE on heartbeat", agent.name, agent_id)

        db.commit()
        db.refresh(agent)
        return {
            "agent_id": agent.id,
            "presence_status": agent.presence_status,
            "device_status": agent.device_status,
            "last_heartbeat_at": agent.last_heartbeat_at.isoformat() if agent.last_heartbeat_at else None
        }

    @staticmethod
    def set_presence(db: Session, agent_id: str, presence_status: str, device_status: Optional[str] = None) -> Dict[str, Any]:
        """Manually sets presence status (AVAILABLE, AWAY, IN_BREAK, WRAP_UP, BUSY, OFFLINE)."""
        valid_states = {"OFFLINE", "AVAILABLE", "RINGING", "BUSY", "WRAP_UP", "AWAY"}
        if presence_status not in valid_states:
            return {"error": f"Invalid presence status: {presence_status}. Valid: {valid_states}"}

        agent = db.query(TeamMember).filter(TeamMember.id == agent_id).first()
        if not agent:
            return {"error": "Agent not found"}

        agent.presence_status = presence_status
        agent.status_updated_at = datetime.utcnow()
        if device_status:
            agent.device_status = device_status

        db.commit()
        db.refresh(agent)
        logger.info("Agent %s (%s) presence set to %s (device=%s)", agent.name, agent_id, agent.presence_status, agent.device_status)
        return {
            "agent_id": agent.id,
            "presence_status": agent.presence_status,
            "device_status": agent.device_status,
            "current_call_id": agent.current_call_id
        }

    @staticmethod
    def get_available_agents(db: Session, organization_id: str = "default-org") -> List[TeamMember]:
        """Queries agents ready to accept incoming handoff calls."""
        AgentPresenceService.cleanup_stale_presence(db)
        heartbeat_cutoff = datetime.utcnow() - timedelta(seconds=25)

        agents = db.query(TeamMember).filter(
            TeamMember.organization_id == organization_id,
            TeamMember.is_active == True,
            TeamMember.presence_status == "AVAILABLE",
            TeamMember.device_status.in_(["REGISTERED", "CONNECTED"]),
            TeamMember.last_heartbeat_at >= heartbeat_cutoff,
            TeamMember.current_call_id == None
        ).all()

        logger.info("Found %d AVAILABLE & healthy agents for organization %s", len(agents), organization_id)
        return agents

    @staticmethod
    def cleanup_stale_presence(db: Session):
        """Automatically transitions agents without a heartbeat in >25s to OFFLINE/UNREACHABLE."""
        stale_cutoff = datetime.utcnow() - timedelta(seconds=25)
        stale_agents = db.query(TeamMember).filter(
            TeamMember.presence_status.in_(["AVAILABLE", "RINGING"]),
            (TeamMember.last_heartbeat_at < stale_cutoff) | (TeamMember.last_heartbeat_at == None)
        ).all()

        if stale_agents:
            for ag in stale_agents:
                logger.warning("Agent %s (%s) heartbeat timed out (>25s) -> Marking OFFLINE / UNREACHABLE", ag.name, ag.id)
                ag.presence_status = "OFFLINE"
                ag.device_status = "UNREACHABLE"
            db.commit()
