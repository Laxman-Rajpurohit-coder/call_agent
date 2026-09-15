import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, Text, JSON, ForeignKey
from sqlalchemy.orm import relationship
from services.dashboard.app.database import Base

def generate_uuid():
    return str(uuid.uuid4())

class Campaign(Base):
    __tablename__ = "campaigns"

    id = Column(String, primary_key=True, default=generate_uuid)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    type = Column(String, nullable=False, default="SCRIPT")  # SCRIPT, AI, HYBRID
    status = Column(String, nullable=False, default="DRAFT") # DRAFT, RUNNING, PAUSED, COMPLETED, FAILED
    script_content = Column(Text, nullable=True)
    voice_model = Column(String, default="hi_pratham")
    max_concurrency = Column(Integer, default=5)
    calls_per_minute = Column(Integer, default=20)
    max_retries = Column(Integer, default=2)
    assigned_agent_id = Column(String, ForeignKey("team_members.id", ondelete="SET NULL"), nullable=True)
    assigned_agent_name = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    contacts = relationship("CampaignContact", back_populates="campaign", cascade="all, delete-orphan")

class CampaignContact(Base):
    __tablename__ = "campaign_contacts"

    id = Column(String, primary_key=True, default=generate_uuid)
    campaign_id = Column(String, ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False)
    contact_id = Column(String, ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False)
    status = Column(String, nullable=False, default="PENDING") # PENDING, QUEUED, CALLING, ANSWERED, COMPLETED, NO_ANSWER, BUSY, FAILED, RETRY
    attempt_count = Column(Integer, default=0)
    last_attempt_at = Column(DateTime, nullable=True)
    final_outcome = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    campaign = relationship("Campaign", back_populates="contacts")
    attempts = relationship("CampaignAttempt", back_populates="campaign_contact", cascade="all, delete-orphan")

class CampaignAttempt(Base):
    __tablename__ = "campaign_attempts"

    id = Column(String, primary_key=True, default=generate_uuid)
    campaign_contact_id = Column(String, ForeignKey("campaign_contacts.id", ondelete="CASCADE"), nullable=False)
    call_id = Column(String, nullable=True)
    idempotency_key = Column(String, unique=True, nullable=True)
    lifecycle_state = Column(String, nullable=False, default="QUEUED")
    attempt_number = Column(Integer, default=1)
    status = Column(String, nullable=False, default="STARTED")
    duration_s = Column(Float, default=0.0)
    failure_reason = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    campaign_contact = relationship("CampaignContact", back_populates="attempts")
