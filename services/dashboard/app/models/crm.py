import uuid
from datetime import datetime
from sqlalchemy import Column, String, Float, Boolean, DateTime, Text, JSON, ForeignKey
from sqlalchemy.orm import relationship
from services.dashboard.app.database import Base

def generate_uuid():
    return str(uuid.uuid4())

class Organization(Base):
    __tablename__ = "organizations"

    id = Column(String, primary_key=True, default=generate_uuid)
    name = Column(String, nullable=False)
    slug = Column(String, nullable=False, unique=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    contacts = relationship("Contact", back_populates="organization", cascade="all, delete-orphan")
    call_sessions = relationship("CallSession", back_populates="organization", cascade="all, delete-orphan")

class Contact(Base):
    __tablename__ = "contacts"

    id = Column(String, primary_key=True, default=generate_uuid)
    organization_id = Column(String, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    phone_number = Column(String, nullable=False)
    name = Column(String, nullable=True)
    email = Column(String, nullable=True)
    status = Column(String, default="lead")
    preferred_language = Column(String, default="hi")
    lead_source = Column(String, default="Direct")  # Google Ads, Facebook Ads, Instagram Ads, Google Sheets, Direct
    lead_owner_id = Column(String, ForeignKey("team_members.id", ondelete="SET NULL"), nullable=True)
    last_called_at = Column(DateTime, nullable=True)
    custom_fields = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    organization = relationship("Organization", back_populates="contacts")
    lead_owner = relationship("TeamMember", back_populates="assigned_contacts", foreign_keys=[lead_owner_id])
    call_sessions = relationship("CallSession", back_populates="contact")
    call_interactions = relationship("CallInteraction", back_populates="contact")
    tasks = relationship("LeadTask", back_populates="contact", cascade="all, delete-orphan")
    reminders = relationship("LeadReminder", back_populates="contact", cascade="all, delete-orphan")

class TeamMember(Base):
    __tablename__ = "team_members"

    id = Column(String, primary_key=True, default=generate_uuid)
    organization_id = Column(String, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, default="default-org")
    name = Column(String, nullable=False)
    email = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    role = Column(String, default="Sales Agent") # Admin, Manager, Sales Agent
    is_active = Column(Boolean, default=True)
    assigned_leads_count = Column(Float, default=0)
    
    # Agent Authentication & Status Fields
    pin_code = Column(String, default="1234")
    status = Column(String, default="available") # available, on_call, in_break, wrap_up, offline
    status_updated_at = Column(DateTime, default=datetime.utcnow)
    sip_extension = Column(String, nullable=True, default="101")
    sip_password = Column(String, nullable=True, default="101pass")
    avatar_url = Column(String, nullable=True)
    daily_call_target = Column(Float, default=50)
    shift_name = Column(String, default="Morning Shift")
    created_at = Column(DateTime, default=datetime.utcnow)

    assigned_contacts = relationship("Contact", back_populates="lead_owner", foreign_keys=[Contact.lead_owner_id])
    assigned_tasks = relationship("LeadTask", back_populates="assigned_to")

class LeadTask(Base):
    __tablename__ = "lead_tasks"

    id = Column(String, primary_key=True, default=generate_uuid)
    organization_id = Column(String, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, default="default-org")
    contact_id = Column(String, ForeignKey("contacts.id", ondelete="CASCADE"), nullable=True)
    assigned_to_id = Column(String, ForeignKey("team_members.id", ondelete="SET NULL"), nullable=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String, default="pending")  # pending, completed, cancelled
    due_at = Column(DateTime, nullable=True)
    custom_inquiry_data = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)

    contact = relationship("Contact", back_populates="tasks")
    assigned_to = relationship("TeamMember", back_populates="assigned_tasks")
    reminders = relationship("LeadReminder", back_populates="task", cascade="all, delete-orphan")

class LeadReminder(Base):
    __tablename__ = "lead_reminders"

    id = Column(String, primary_key=True, default=generate_uuid)
    organization_id = Column(String, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, default="default-org")
    contact_id = Column(String, ForeignKey("contacts.id", ondelete="CASCADE"), nullable=True)
    task_id = Column(String, ForeignKey("lead_tasks.id", ondelete="CASCADE"), nullable=True)
    note = Column(String, nullable=False)
    remind_at = Column(DateTime, nullable=False)
    is_triggered = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    contact = relationship("Contact", back_populates="reminders")
    task = relationship("LeadTask", back_populates="reminders")

class WhatsAppMessage(Base):
    __tablename__ = "whatsapp_messages"

    id = Column(String, primary_key=True, default=generate_uuid)
    organization_id = Column(String, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, default="default-org")
    contact_id = Column(String, ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True)
    phone_number = Column(String, nullable=False)
    direction = Column(String, nullable=False, default="outbound")  # inbound, outbound
    message_text = Column(Text, nullable=False)
    status = Column(String, default="sent")  # sent, delivered, read, failed
    timestamp = Column(DateTime, default=datetime.utcnow)

class CallSession(Base):
    __tablename__ = "call_sessions"

    id = Column(String, primary_key=True, default=generate_uuid)
    organization_id = Column(String, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    contact_id = Column(String, ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True)
    provider = Column(String, nullable=False, default="audiosocket")
    direction = Column(String, nullable=False, default="inbound")
    dial_mode = Column(String, nullable=False, default="app")  # app (Wi-Fi/SIP), sim (GSM/Cellular)
    from_number = Column(String, nullable=False)
    to_number = Column(String, nullable=False)
    status = Column(String, nullable=False, default="initiated")
    started_at = Column(DateTime, nullable=True)
    answered_at = Column(DateTime, nullable=True)
    ended_at = Column(DateTime, nullable=True)
    duration_s = Column(Float, default=0.0)
    recording_url = Column(String, nullable=True)
    transcript = Column(JSON, default=list)
    custom_fields = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    organization = relationship("Organization", back_populates="call_sessions")
    contact = relationship("Contact", back_populates="call_sessions")
    interactions = relationship("CallInteraction", back_populates="call_session", cascade="all, delete-orphan")

class CallInteraction(Base):
    __tablename__ = "call_interactions"

    id = Column(String, primary_key=True, default=generate_uuid)
    call_id = Column(String, ForeignKey("call_sessions.id", ondelete="CASCADE"), nullable=False)
    contact_id = Column(String, ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True)
    intent_detected = Column(String, nullable=True)
    confidence = Column(Float, default=0.0)
    ai_summary = Column(Text, nullable=True)
    human_handoff_requested = Column(Boolean, default=False)
    followup_required = Column(Boolean, default=False)
    followup_date = Column(DateTime, nullable=True)
    custom_fields = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)

    call_session = relationship("CallSession", back_populates="interactions")
    contact = relationship("Contact", back_populates="call_interactions")

    @property
    def call_session_id(self):
        return self.call_id

    @call_session_id.setter
    def call_session_id(self, val):
        self.call_id = val


