import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, Text, JSON, ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import relationship
from services.dashboard.app.database import Base

def generate_uuid():
    return str(uuid.uuid4())

class Organization(Base):
    __tablename__ = "organizations"

    id = Column(String, primary_key=True, default=generate_uuid)
    name = Column(String, nullable=False)                         # e.g., "Smile Dental Clinic"
    slug = Column(String, nullable=False, unique=True, index=True)# e.g., "smile-dental"
    industry = Column(String, default="Healthcare / Dental")
    country = Column(String, default="India")
    timezone = Column(String, default="Asia/Kolkata")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 1:1 Configurations
    portal_config = relationship("PortalConfig", back_populates="organization", uselist=False, cascade="all, delete-orphan")
    agent_config = relationship("AgentConfig", back_populates="organization", uselist=False, cascade="all, delete-orphan")

    # 1:N Collections
    services = relationship("Service", back_populates="organization", cascade="all, delete-orphan")
    phone_numbers = relationship("PhoneNumber", back_populates="organization", cascade="all, delete-orphan")
    business_hours = relationship("BusinessHours", back_populates="organization", cascade="all, delete-orphan")
    team_members = relationship("TeamMember", back_populates="organization", cascade="all, delete-orphan")
    contacts = relationship("Contact", back_populates="organization", cascade="all, delete-orphan")
    contact_phones = relationship("ContactPhone", back_populates="organization", cascade="all, delete-orphan")
    contact_emails = relationship("ContactEmail", back_populates="organization", cascade="all, delete-orphan")
    contact_notes = relationship("ContactNote", back_populates="organization", cascade="all, delete-orphan")
    campaigns = relationship("Campaign", back_populates="organization", cascade="all, delete-orphan")
    call_sessions = relationship("CallSession", back_populates="organization", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="organization", cascade="all, delete-orphan")

class PortalConfig(Base):
    __tablename__ = "portal_configs"

    id = Column(String, primary_key=True, default=generate_uuid)
    organization_id = Column(String, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    portal_name = Column(String, nullable=True)                  # e.g., "Smile Dental AI CRM"
    subtitle = Column(String, default="AI Receptionist & Lead Management")
    theme_primary = Column(String, default="#6366f1")             # Primary Brand Color
    theme_bg = Column(String, default="#0f172a")
    logo_icon = Column(String, default="⚡")
    logo_url = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    organization = relationship("Organization", back_populates="portal_config")

class AgentConfig(Base):
    __tablename__ = "agent_configs"

    id = Column(String, primary_key=True, default=generate_uuid)
    organization_id = Column(String, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    agent_name = Column(String, default="Riya")                  # Persona Name
    voice_model = Column(String, default="cartesia_hi_sonic")    # TTS Model
    language = Column(String, default="hi")                      # hi / en / bilingual
    system_instructions = Column(Text, nullable=True)            # Clinic-specific notes
    max_call_duration_s = Column(Integer, default=300)
    # Per-organization label sets for post-call analysis (NULL = use built-in defaults)
    allowed_intents = Column(JSON, nullable=True)
    allowed_lead_labels = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    organization = relationship("Organization", back_populates="agent_config")

class Service(Base):
    __tablename__ = "services"

    id = Column(String, primary_key=True, default=generate_uuid)
    organization_id = Column(String, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String, nullable=False)                        # e.g., "Root Canal Treatment"
    description = Column(String, nullable=True)
    price = Column(Float, nullable=True)                         # Price in INR
    duration_mins = Column(Integer, default=30)
    category = Column(String, default="General")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    organization = relationship("Organization", back_populates="services")

class PhoneNumber(Base):
    __tablename__ = "phone_numbers"

    id = Column(String, primary_key=True, default=generate_uuid)
    organization_id = Column(String, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    phone_number = Column(String, nullable=False, index=True)   # e.g. "+918830718466"
    provider = Column(String, default="Exotel")                  # Exotel, Twilio, SIP
    purpose = Column(String, default="reception")                # reception, sales, campaign
    is_primary = Column(Boolean, default=True)
    status = Column(String, default="active")
    created_at = Column(DateTime, default=datetime.utcnow)

    organization = relationship("Organization", back_populates="phone_numbers")

class BusinessHours(Base):
    __tablename__ = "business_hours"

    id = Column(String, primary_key=True, default=generate_uuid)
    organization_id = Column(String, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    day_of_week = Column(Integer, nullable=False)                # 0=Monday ... 6=Sunday
    is_open = Column(Boolean, default=True)
    open_time = Column(String, default="09:00")                  # "09:00"
    close_time = Column(String, default="18:00")                 # "18:00"

    organization = relationship("Organization", back_populates="business_hours")

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(String, primary_key=True, default=generate_uuid)
    organization_id = Column(String, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String, nullable=True)
    action = Column(String, nullable=False)                      # PORTAL_CREATED, LEAD_CONTACTED, etc.
    resource_type = Column(String, nullable=False)              # portal, lead, campaign
    resource_id = Column(String, nullable=True)
    meta_info = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    organization = relationship("Organization", back_populates="audit_logs")

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
    company = Column(String, nullable=True)
    is_archived = Column(Boolean, default=False)
    is_blocked = Column(Boolean, default=False)
    tags = Column(JSON, default=list)
    ai_profile = Column(JSON, default=dict)
    merged_into_id = Column(String, ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    organization = relationship("Organization", back_populates="contacts")
    lead_owner = relationship("TeamMember", back_populates="assigned_contacts", foreign_keys=[lead_owner_id])
    call_sessions = relationship("CallSession", back_populates="contact")
    call_interactions = relationship("CallInteraction", back_populates="contact")
    tasks = relationship("LeadTask", back_populates="contact", cascade="all, delete-orphan")
    reminders = relationship("LeadReminder", back_populates="contact", cascade="all, delete-orphan")
    phones = relationship("ContactPhone", back_populates="contact", cascade="all, delete-orphan")
    emails = relationship("ContactEmail", back_populates="contact", cascade="all, delete-orphan")
    notes = relationship("ContactNote", back_populates="contact", cascade="all, delete-orphan", order_by="desc(ContactNote.created_at)")

class ContactPhone(Base):
    __tablename__ = "contact_phones"
    __table_args__ = (UniqueConstraint("organization_id", "phone_e164", name="uq_org_phone"),)

    id = Column(String, primary_key=True, default=generate_uuid)
    contact_id = Column(String, ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False, index=True)
    organization_id = Column(String, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    phone_e164 = Column(String, nullable=False, index=True)
    phone_type = Column(String, default="mobile")  # mobile, work, home, whatsapp
    is_primary = Column(Boolean, default=True)
    verified = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    organization = relationship("Organization", back_populates="contact_phones")
    contact = relationship("Contact", back_populates="phones")

class ContactEmail(Base):
    __tablename__ = "contact_emails"

    id = Column(String, primary_key=True, default=generate_uuid)
    contact_id = Column(String, ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False, index=True)
    organization_id = Column(String, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    email = Column(String, nullable=False, index=True)
    email_type = Column(String, default="work")  # work, personal
    is_primary = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    organization = relationship("Organization", back_populates="contact_emails")
    contact = relationship("Contact", back_populates="emails")

class ContactNote(Base):
    __tablename__ = "contact_notes"

    id = Column(String, primary_key=True, default=generate_uuid)
    contact_id = Column(String, ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False, index=True)
    organization_id = Column(String, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    agent_id = Column(String, ForeignKey("team_members.id", ondelete="SET NULL"), nullable=True)
    agent_name = Column(String, nullable=True)
    note = Column(Text, nullable=False)
    disposition = Column(String, nullable=True)  # Interested, Callback, Converted, Do Not Call, Wrong Number, etc.
    sentiment = Column(String, nullable=True)     # positive, neutral, negative
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    organization = relationship("Organization", back_populates="contact_notes")
    contact = relationship("Contact", back_populates="notes")
    agent = relationship("TeamMember")

class TeamMember(Base):
    __tablename__ = "team_members"

    id = Column(String, primary_key=True, default=generate_uuid)
    organization_id = Column(String, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, default="default-org", index=True)
    name = Column(String, nullable=False)
    email = Column(String, nullable=True, index=True)
    phone = Column(String, nullable=True)
    role = Column(String, default="AGENT") # OWNER, ADMIN, MANAGER, AGENT, VIEWER
    is_active = Column(Boolean, default=True)
    assigned_leads_count = Column(Float, default=0)
    password_hash = Column(String, nullable=True)
    
    # Agent Authentication & Status Fields
    pin_code = Column(String, default="1234")
    status = Column(String, default="available") # available, on_call, in_break, wrap_up, offline
    presence_status = Column(String, default="AVAILABLE") # OFFLINE, AVAILABLE, RINGING, BUSY, WRAP_UP, AWAY
    device_status = Column(String, default="REGISTERED") # REGISTERED, CONNECTED, UNREACHABLE
    last_heartbeat_at = Column(DateTime, default=datetime.utcnow)
    current_call_id = Column(String, nullable=True)
    telephony_provider = Column(String, default="WebRTC")
    telephony_endpoint = Column(String, nullable=True)
    status_updated_at = Column(DateTime, default=datetime.utcnow)
    sip_extension = Column(String, nullable=True, default="101")
    sip_password = Column(String, nullable=True, default="101pass")
    avatar_url = Column(String, nullable=True)
    daily_call_target = Column(Float, default=50)
    shift_name = Column(String, default="Morning Shift")
    created_at = Column(DateTime, default=datetime.utcnow)

    organization = relationship("Organization", back_populates="team_members")
    assigned_contacts = relationship("Contact", back_populates="lead_owner", foreign_keys=[Contact.lead_owner_id])
    assigned_tasks = relationship("LeadTask", back_populates="assigned_to")
    campaign_memberships = relationship("CampaignAgent", back_populates="user", cascade="all, delete-orphan")

class LeadTask(Base):
    __tablename__ = "lead_tasks"

    id = Column(String, primary_key=True, default=generate_uuid)
    organization_id = Column(String, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, default="default-org", index=True)
    contact_id = Column(String, ForeignKey("contacts.id", ondelete="CASCADE"), nullable=True)
    assigned_to_id = Column(String, ForeignKey("team_members.id", ondelete="SET NULL"), nullable=True, index=True)
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
    organization_id = Column(String, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, default="default-org", index=True)
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
    organization_id = Column(String, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, default="default-org", index=True)
    contact_id = Column(String, ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True)
    phone_number = Column(String, nullable=False)
    direction = Column(String, nullable=False, default="outbound")  # inbound, outbound
    message_text = Column(Text, nullable=False)
    status = Column(String, default="sent")  # sent, delivered, read, failed
    timestamp = Column(DateTime, default=datetime.utcnow)

class CallSession(Base):
    __tablename__ = "call_sessions"

    incoming_config_id = Column(String, ForeignKey("incoming_call_configs.id", ondelete="SET NULL"), nullable=True, index=True)
    config_version = Column(Integer, nullable=True)
    config_snapshot = Column(JSON, nullable=True)

    id = Column(String, primary_key=True, default=generate_uuid)
    organization_id = Column(String, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    contact_id = Column(String, ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True)
    handled_by_user_id = Column(String, ForeignKey("team_members.id", ondelete="SET NULL"), nullable=True, index=True)
    recording_storage_key = Column(String, nullable=True)
    provider = Column(String, nullable=False, default="audiosocket")
    direction = Column(String, nullable=False, default="inbound")
    dial_mode = Column(String, nullable=False, default="app")  # app (Wi-Fi/SIP), sim (GSM/Cellular)
    from_number = Column(String, nullable=False)
    to_number = Column(String, nullable=False)
    status = Column(String, nullable=False, default="initiated")
    
    # Handoff Engine & State Machine Fields
    handoff_status = Column(String, default="NONE") # NONE, WAITING_FOR_AGENT, AGENT_ACCEPTED, BRIDGING, HUMAN_CONNECTED, FAILED_NO_AGENTS, REJECTED, BRIDGE_FAILED, CANCELLED
    handoff_reason = Column(String, nullable=True) # CUSTOMER_REQUESTED_HUMAN, AI_OUT_OF_SCOPE, AI_LOW_CONFIDENCE, CUSTOMER_ESCALATION
    handoff_failure_reason = Column(String, nullable=True) # NO_AVAILABLE_AGENTS, NO_ANSWER_TIMEOUT, ALL_AGENTS_REJECTED, TELEPHONY_FAILURE, BRIDGE_FAILURE, CALLER_HUNG_UP
    customer_disconnected = Column(Boolean, default=False)
    ai_summary = Column(Text, nullable=True)
    accepted_at = Column(DateTime, nullable=True)
    bridge_started_at = Column(DateTime, nullable=True)
    human_connected_at = Column(DateTime, nullable=True)
    idempotency_key = Column(String, nullable=True, index=True)
    # Post-call analysis lifecycle: PENDING -> DONE | FAILED (LEGACY = pre-existing rows, never analysed)
    analysis_status = Column(String, default="PENDING", nullable=True, index=True)

    started_at = Column(DateTime, nullable=True)
    answered_at = Column(DateTime, nullable=True)
    ended_at = Column(DateTime, nullable=True)
    last_heartbeat_at = Column(DateTime, default=datetime.utcnow, nullable=True)
    media_status = Column(String, default="INACTIVE", nullable=True) # RECEIVING, SENDING, DEGRADED, INACTIVE, DISCONNECTED
    vad_state = Column(String, default="IDLE", nullable=True) # IDLE, LISTENING, SPEAKING
    duration_s = Column(Float, default=0.0)
    recording_url = Column(String, nullable=True)
    transcript = Column(JSON, default=list)
    custom_fields = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    organization = relationship("Organization", back_populates="call_sessions")
    contact = relationship("Contact", back_populates="call_sessions")
    handled_by = relationship("TeamMember", foreign_keys=[handled_by_user_id])
    interactions = relationship("CallInteraction", back_populates="call_session", cascade="all, delete-orphan")
    handoff_attempts = relationship("CallHandoffAttempt", back_populates="call_session", cascade="all, delete-orphan")

class CallHandoffAttempt(Base):
    __tablename__ = "call_handoff_attempts"

    id = Column(String, primary_key=True, default=generate_uuid)
    call_session_id = Column(String, ForeignKey("call_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    agent_id = Column(String, ForeignKey("team_members.id", ondelete="CASCADE"), nullable=False, index=True)
    offered_at = Column(DateTime, default=datetime.utcnow)
    ring_started_at = Column(DateTime, nullable=True)
    answered_at = Column(DateTime, nullable=True)
    rejected_at = Column(DateTime, nullable=True)
    cancelled_at = Column(DateTime, nullable=True)
    result = Column(String, nullable=True) # ANSWERED, REJECTED, CANCELLED_OTHER_WON, TIMEOUT, DEVICE_UNREACHABLE, CALLER_HUNG_UP

    call_session = relationship("CallSession", back_populates="handoff_attempts")
    agent = relationship("TeamMember")

class CallInteraction(Base):
    __tablename__ = "call_interactions"

    id = Column(String, primary_key=True, default=generate_uuid)
    organization_id = Column(String, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    call_id = Column(String, ForeignKey("call_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    contact_id = Column(String, ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True)
    intent_detected = Column(String, nullable=True)
    confidence = Column(Float, default=0.0)
    ai_summary = Column(Text, nullable=True)
    human_handoff_requested = Column(Boolean, default=False)
    followup_required = Column(Boolean, default=False)
    followup_date = Column(DateTime, nullable=True)
    # Unified intent / lead labelling (services/dashboard/app/services/call_analysis.py)
    lead_label = Column(String, nullable=True, index=True)   # hot, warm, cold, not_interested, callback, wrong_number, do_not_call, no_conversation, needs_review
    evidence_quote = Column(Text, nullable=True)             # exact caller words that justify the label
    model_name = Column(String, nullable=True)
    prompt_version = Column(String, nullable=True)
    sentiment = Column(String, nullable=True)                # POSITIVE, NEUTRAL, NEGATIVE, FRUSTRATED
    is_agent_corrected = Column(Boolean, default=False)
    corrected_by_user_id = Column(String, ForeignKey("team_members.id", ondelete="SET NULL"), nullable=True)
    agent_notes = Column(Text, nullable=True)
    custom_fields = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)

    organization = relationship("Organization")
    call_session = relationship("CallSession", back_populates="interactions")
    contact = relationship("Contact", back_populates="call_interactions")

    @property
    def call_session_id(self):
        return self.call_id

    @call_session_id.setter
    def call_session_id(self, val):
        self.call_id = val



class IncomingCallConfig(Base):
    __tablename__ = "incoming_call_configs"

    id = Column(String, primary_key=True, default=generate_uuid)
    organization_id = Column(String, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    phone_number_id = Column(String, ForeignKey("phone_numbers.id", ondelete="SET NULL"), nullable=True, index=True)
    
    name = Column(String, nullable=False)
    is_active = Column(Boolean, default=True, index=True)
    priority = Column(Integer, default=0)
    config_version = Column(Integer, default=1)

    ai_model = Column(String, default="gpt-4o")
    voice_provider = Column(String, default="cartesia")
    voice_id = Column(String, default="cartesia_hi_sonic")
    speaking_style = Column(String, default="Friendly")
    temperature = Column(Float, default=0.3)

    ai_name = Column(String, default="Ananya")
    role_description = Column(Text, nullable=True)
    primary_objective = Column(Text, nullable=True)
    behavior_rules = Column(JSON, default=list)
    system_instructions = Column(Text, nullable=True)

    primary_language = Column(String, default="en")
    supported_languages = Column(JSON, default=list)
    auto_detect_language = Column(Boolean, default=True)
    allow_language_switching = Column(Boolean, default=True)
    language_priority = Column(JSON, default=list)

    auto_answer = Column(Boolean, default=True)
    ring_timeout_s = Column(Integer, default=15)
    max_call_duration_s = Column(Integer, nullable=True)
    max_ai_duration_s = Column(Integer, nullable=True)

    business_name = Column(String, nullable=True)
    business_description = Column(Text, nullable=True)
    services_offered = Column(JSON, default=list)
    faq_knowledge_base = Column(Text, nullable=True)

    auto_create_contact = Column(Boolean, default=True)
    generate_ai_summary = Column(Boolean, default=True)
    extract_intent = Column(Boolean, default=True)
    auto_tags = Column(JSON, default=list)

    recording_enabled = Column(Boolean, default=True)
    transcription_enabled = Column(Boolean, default=True)
    transcript_language = Column(String, default="en")

    greeting_message = Column(Text, nullable=True)
    auto_generate_greeting = Column(Boolean, default=False)

    outside_hours_action = Column(String, default="continue_ai")

    transfer_enabled = Column(Boolean, default=True)
    transfer_triggers = Column(JSON, default=list)
    transfer_confidence_threshold = Column(Float, default=0.65)
    transfer_timeout_s = Column(Integer, default=15)
    transfer_team_id = Column(String, nullable=True)
    ring_strategy = Column(String, default="first_available")
    no_answer_action = Column(String, default="voicemail")

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    organization = relationship("Organization")
    phone_number = relationship("PhoneNumber")


class IncomingCallConfigAudit(Base):
    __tablename__ = "incoming_call_config_audits"

    id = Column(String, primary_key=True, default=generate_uuid)
    config_id = Column(String, ForeignKey("incoming_call_configs.id", ondelete="CASCADE"), nullable=False, index=True)
    organization_id = Column(String, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    changed_by_user_id = Column(String, ForeignKey("team_members.id", ondelete="SET NULL"), nullable=True)
    changed_at = Column(DateTime, default=datetime.utcnow)
    changes = Column(JSON, nullable=False)
    config_version = Column(Integer, nullable=False)
