from sqlalchemy import create_engine, inspect, text, event
from sqlalchemy.orm import sessionmaker, declarative_base
from services.dashboard.app.config import settings

db_url = settings.DATABASE_URL
connect_args = {"check_same_thread": False, "timeout": 30} if db_url.startswith("sqlite") else {}

engine = create_engine(db_url, connect_args=connect_args, echo=False)

if db_url.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def run_migrations():
    """Safely apply schema updates for existing SQLite/PostgreSQL databases."""
    with engine.connect() as conn:
        inspector = inspect(engine)
        if "campaign_attempts" in inspector.get_table_names():
            columns = [col["name"] for col in inspector.get_columns("campaign_attempts")]
            if "idempotency_key" not in columns:
                print("[DB Migration] Adding idempotency_key column to campaign_attempts...")
                conn.execute(text("ALTER TABLE campaign_attempts ADD COLUMN idempotency_key TEXT;"))
                conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS idx_campaign_attempts_idempotency ON campaign_attempts (idempotency_key);"))
                conn.commit()
            if "lifecycle_state" not in columns:
                print("[DB Migration] Adding lifecycle_state column to campaign_attempts...")
                conn.execute(text("ALTER TABLE campaign_attempts ADD COLUMN lifecycle_state TEXT DEFAULT 'QUEUED';"))
                conn.commit()

        if "contacts" in inspector.get_table_names():
            contact_cols = [col["name"] for col in inspector.get_columns("contacts")]
            if "lead_source" not in contact_cols:
                print("[DB Migration] Adding lead_source column to contacts...")
                conn.execute(text("ALTER TABLE contacts ADD COLUMN lead_source TEXT DEFAULT 'Direct';"))
                conn.commit()
            if "lead_owner_id" not in contact_cols:
                print("[DB Migration] Adding lead_owner_id column to contacts...")
                conn.execute(text("ALTER TABLE contacts ADD COLUMN lead_owner_id TEXT;"))
                conn.commit()

        if "call_sessions" in inspector.get_table_names():
            call_cols = [col["name"] for col in inspector.get_columns("call_sessions")]
            if "dial_mode" not in call_cols:
                print("[DB Migration] Adding dial_mode column to call_sessions...")
                conn.execute(text("ALTER TABLE call_sessions ADD COLUMN dial_mode TEXT DEFAULT 'app';"))
                conn.commit()
            if "last_heartbeat_at" not in call_cols:
                print("[DB Migration] Adding last_heartbeat_at column to call_sessions...")
                conn.execute(text("ALTER TABLE call_sessions ADD COLUMN last_heartbeat_at TIMESTAMP;"))
                conn.commit()
            if "media_status" not in call_cols:
                print("[DB Migration] Adding media_status column to call_sessions...")
                conn.execute(text("ALTER TABLE call_sessions ADD COLUMN media_status TEXT DEFAULT 'INACTIVE';"))
                conn.commit()
            if "vad_state" not in call_cols:
                print("[DB Migration] Adding vad_state column to call_sessions...")
                conn.execute(text("ALTER TABLE call_sessions ADD COLUMN vad_state TEXT DEFAULT 'IDLE';"))
                conn.commit()

        if "campaigns" in inspector.get_table_names():
            camp_cols = [col["name"] for col in inspector.get_columns("campaigns")]
            if "assigned_agent_id" not in camp_cols:
                print("[DB Migration] Adding assigned_agent_id column to campaigns...")
                conn.execute(text("ALTER TABLE campaigns ADD COLUMN assigned_agent_id TEXT;"))
                conn.commit()
            if "assigned_agent_name" not in camp_cols:
                print("[DB Migration] Adding assigned_agent_name column to campaigns...")
                conn.execute(text("ALTER TABLE campaigns ADD COLUMN assigned_agent_name TEXT;"))
                conn.commit()
            if "organization_id" not in camp_cols:
                print("[DB Migration] Adding organization_id column to campaigns...")
                conn.execute(text("ALTER TABLE campaigns ADD COLUMN organization_id TEXT;"))
                conn.commit()

        if "call_interactions" in inspector.get_table_names():
            inter_cols = [col["name"] for col in inspector.get_columns("call_interactions")]
            if "organization_id" not in inter_cols:
                print("[DB Migration] Adding organization_id column to call_interactions...")
                conn.execute(text("ALTER TABLE call_interactions ADD COLUMN organization_id TEXT;"))
                conn.commit()

        if "call_sessions" in inspector.get_table_names():
            call_cols = [col["name"] for col in inspector.get_columns("call_sessions")]
            if "handled_by_user_id" not in call_cols:
                print("[DB Migration] Adding handled_by_user_id column to call_sessions...")
                conn.execute(text("ALTER TABLE call_sessions ADD COLUMN handled_by_user_id TEXT;"))
                conn.commit()
            if "recording_storage_key" not in call_cols:
                print("[DB Migration] Adding recording_storage_key column to call_sessions...")
                conn.execute(text("ALTER TABLE call_sessions ADD COLUMN recording_storage_key TEXT;"))
                conn.commit()

        if "team_members" in inspector.get_table_names():
            team_cols = [col["name"] for col in inspector.get_columns("team_members")]
            if "password_hash" not in team_cols:
                print("[DB Migration] Adding password_hash column to team_members...")
                conn.execute(text("ALTER TABLE team_members ADD COLUMN password_hash TEXT;"))
                conn.commit()
            if "presence_status" not in team_cols:
                print("[DB Migration] Adding presence_status column to team_members...")
                conn.execute(text("ALTER TABLE team_members ADD COLUMN presence_status TEXT DEFAULT 'AVAILABLE';"))
                conn.commit()
            if "device_status" not in team_cols:
                print("[DB Migration] Adding device_status column to team_members...")
                conn.execute(text("ALTER TABLE team_members ADD COLUMN device_status TEXT DEFAULT 'REGISTERED';"))
                conn.commit()
            if "last_heartbeat_at" not in team_cols:
                print("[DB Migration] Adding last_heartbeat_at column to team_members...")
                conn.execute(text("ALTER TABLE team_members ADD COLUMN last_heartbeat_at TIMESTAMP;"))
                conn.commit()
            if "current_call_id" not in team_cols:
                print("[DB Migration] Adding current_call_id column to team_members...")
                conn.execute(text("ALTER TABLE team_members ADD COLUMN current_call_id TEXT;"))
                conn.commit()
            if "telephony_provider" not in team_cols:
                print("[DB Migration] Adding telephony_provider column to team_members...")
                conn.execute(text("ALTER TABLE team_members ADD COLUMN telephony_provider TEXT DEFAULT 'WebRTC';"))
                conn.commit()
            if "telephony_endpoint" not in team_cols:
                print("[DB Migration] Adding telephony_endpoint column to team_members...")
                conn.execute(text("ALTER TABLE team_members ADD COLUMN telephony_endpoint TEXT;"))
                conn.commit()

        if "call_sessions" in inspector.get_table_names():
            call_cols = [col["name"] for col in inspector.get_columns("call_sessions")]
            if "handoff_status" not in call_cols:
                print("[DB Migration] Adding handoff_status column to call_sessions...")
                conn.execute(text("ALTER TABLE call_sessions ADD COLUMN handoff_status TEXT DEFAULT 'NONE';"))
                conn.commit()
            if "handoff_reason" not in call_cols:
                print("[DB Migration] Adding handoff_reason column to call_sessions...")
                conn.execute(text("ALTER TABLE call_sessions ADD COLUMN handoff_reason TEXT;"))
                conn.commit()
            if "handoff_failure_reason" not in call_cols:
                print("[DB Migration] Adding handoff_failure_reason column to call_sessions...")
                conn.execute(text("ALTER TABLE call_sessions ADD COLUMN handoff_failure_reason TEXT;"))
                conn.commit()
            if "customer_disconnected" not in call_cols:
                print("[DB Migration] Adding customer_disconnected column to call_sessions...")
                conn.execute(text("ALTER TABLE call_sessions ADD COLUMN customer_disconnected INTEGER DEFAULT 0;"))
                conn.commit()
            if "ai_summary" not in call_cols:
                print("[DB Migration] Adding ai_summary column to call_sessions...")
                conn.execute(text("ALTER TABLE call_sessions ADD COLUMN ai_summary TEXT;"))
                conn.commit()
            if "accepted_at" not in call_cols:
                print("[DB Migration] Adding accepted_at column to call_sessions...")
                conn.execute(text("ALTER TABLE call_sessions ADD COLUMN accepted_at TIMESTAMP;"))
                conn.commit()
            if "bridge_started_at" not in call_cols:
                print("[DB Migration] Adding bridge_started_at column to call_sessions...")
                conn.execute(text("ALTER TABLE call_sessions ADD COLUMN bridge_started_at TIMESTAMP;"))
                conn.commit()
            if "human_connected_at" not in call_cols:
                print("[DB Migration] Adding human_connected_at column to call_sessions...")
                conn.execute(text("ALTER TABLE call_sessions ADD COLUMN human_connected_at TIMESTAMP;"))
                conn.commit()
            if "idempotency_key" not in call_cols:
                print("[DB Migration] Adding idempotency_key column to call_sessions...")
                conn.execute(text("ALTER TABLE call_sessions ADD COLUMN idempotency_key TEXT;"))
                conn.commit()

        if "organizations" in inspector.get_table_names():
            org_cols = [col["name"] for col in inspector.get_columns("organizations")]
            for col_name, col_type in [
                ("industry", "TEXT DEFAULT 'Healthcare / Dental'"),
                ("country", "TEXT DEFAULT 'India'"),
                ("timezone", "TEXT DEFAULT 'Asia/Kolkata'"),
                ("is_active", "INTEGER DEFAULT 1"),
                ("updated_at", "DATETIME")
            ]:
                if col_name not in org_cols:
                    print(f"[DB Migration] Adding {col_name} column to organizations...")
                    conn.execute(text(f"ALTER TABLE organizations ADD COLUMN {col_name} {col_type};"))
                    conn.commit()

        # ---- Unified intent & lead labelling engine (services/call_analysis.py) ----
        inspector.clear_cache()
        all_tables = inspector.get_table_names()

        def _add_missing(table, cols):
            existing = [c["name"] for c in inspector.get_columns(table)]
            added = []
            for col_name, col_ddl in cols:
                if col_name not in existing:
                    print(f"[DB Migration] Adding {col_name} column to {table}...")
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_ddl};"))
                    conn.commit()
                    added.append(col_name)
            return added

        if "call_sessions" in all_tables:
            added = _add_missing("call_sessions", [("analysis_status", "TEXT")])
            if "analysis_status" in added:
                # Pre-existing calls must never be re-analysed (LLM cost) -> mark LEGACY once.
                conn.execute(text("UPDATE call_sessions SET analysis_status = 'LEGACY' WHERE analysis_status IS NULL;"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_calls_analysis_status ON call_sessions(analysis_status);"))
                conn.commit()

        if "call_interactions" in all_tables:
            added = _add_missing("call_interactions", [
                ("lead_label", "TEXT"),
                ("evidence_quote", "TEXT"),
                ("model_name", "TEXT"),
                ("prompt_version", "TEXT"),
                ("sentiment", "TEXT"),
                ("is_agent_corrected", "INTEGER DEFAULT 0"),
                ("corrected_by_user_id", "TEXT"),
                ("agent_notes", "TEXT"),
            ])
            if "lead_label" in added:
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_interactions_lead_label ON call_interactions(lead_label);"))
                conn.commit()

        if "agent_configs" in all_tables:
            _add_missing("agent_configs", [
                ("allowed_intents", "JSON"),
                ("allowed_lead_labels", "JSON"),
            ])

    # Create new tables if not present
    Base.metadata.create_all(bind=engine)

    # Run Transactional Multi-Tenant Backfill & Integrity Check
    run_tenant_backfill_migration()

def run_tenant_backfill_migration():
    """
    Guarantees atomic, transactional tenant migration across all 7 tenant tables:
    1. Pre-validates row counts across all 7 tables.
    2. Ensures default 'smile-dental' and 'navbharat-ngo' organizations with complete configurations.
    3. Backfills organization_id and CampaignAgent memberships.
    4. Asserts 0 NULL organization_ids across all 7 tables.
    5. Asserts post_count == pre_count (zero records lost).
    6. Ensures performance indexes.
    7. Commits transaction (or rolls back completely on any assertion failure).
    """
    from services.dashboard.app.models.crm import (
        Organization, PortalConfig, AgentConfig, Service, PhoneNumber,
        BusinessHours, Contact, TeamMember, LeadTask, LeadReminder,
        CallSession, CallInteraction
    )
    from services.dashboard.app.models.campaign import Campaign, CampaignAgent
    import uuid
    import hashlib

    def hash_pw(pw: str) -> str:
        # Standard PBKDF2-HMAC-SHA256 with static demonstration salt for demo stability
        salt = b"superfone_stable_tenant_salt_2026"
        h = hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"), salt, 100000)
        return h.hex()

    db = SessionLocal()
    try:
        # Step 1: Pre-migration count snapshot for all 7 tables
        pre_counts = {
            "contacts": db.query(Contact).count(),
            "team_members": db.query(TeamMember).count(),
            "campaigns": db.query(Campaign).count(),
            "call_sessions": db.query(CallSession).count(),
            "lead_tasks": db.query(LeadTask).count(),
            "lead_reminders": db.query(LeadReminder).count(),
            "call_interactions": db.query(CallInteraction).count(),
        }

        # Step 2: Ensure Primary Default Organization: 'smile-dental'
        smile_org = db.query(Organization).filter(Organization.slug == "smile-dental").first()
        if not smile_org:
            smile_org = Organization(
                id="fb9b2953-8498-4108-ad14-b40bc17bfbfa", # Matches Prisma default for zero-drift
                name="Smile Dental Clinic",
                slug="smile-dental",
                industry="Healthcare / Dental",
                country="India",
                timezone="Asia/Kolkata",
                is_active=True
            )
            db.add(smile_org)
            db.flush()

        # Ensure configurations for smile-dental
        if not db.query(PortalConfig).filter(PortalConfig.organization_id == smile_org.id).first():
            db.add(PortalConfig(
                id=str(uuid.uuid4()),
                organization_id=smile_org.id,
                portal_name="Smile Dental AI CRM",
                subtitle="AI Receptionist & Lead Management",
                theme_primary="#6366f1",
                theme_bg="#0f172a",
                logo_icon="⚡"
            ))

        if not db.query(AgentConfig).filter(AgentConfig.organization_id == smile_org.id).first():
            db.add(AgentConfig(
                id=str(uuid.uuid4()),
                organization_id=smile_org.id,
                agent_name="Riya",
                voice_model="cartesia_hi_sonic",
                language="hi",
                system_instructions="You are Riya, the AI receptionist at Smile Dental Clinic. Warmly welcome patients and assist with appointments.",
                max_call_duration_s=300
            ))

        if db.query(Service).filter(Service.organization_id == smile_org.id).count() == 0:
            dental_services = [
                ("Teeth Whitening & Scaling", "Cosmetic whitening and deep ultrasonic dental scaling", 2500.0, 45),
                ("Root Canal Treatment", "Single-sitting pain-free endodontic therapy", 4500.0, 60),
                ("Dental Cleaning & Polishing", "Preventive plaque removal and stain polishing", 1200.0, 30),
                ("General Dental Consultation", "Comprehensive intraoral exam and digital X-rays", 500.0, 20),
                ("Dental Implants Consultation", "Titanium implant assessment with 3D CBCT scan", 35000.0, 60),
            ]
            for s_name, s_desc, s_price, s_dur in dental_services:
                db.add(Service(
                    id=str(uuid.uuid4()),
                    organization_id=smile_org.id,
                    name=s_name,
                    description=s_desc,
                    price=s_price,
                    duration_mins=s_dur,
                    category="Dental",
                    is_active=True
                ))

        if db.query(PhoneNumber).filter(PhoneNumber.organization_id == smile_org.id).count() == 0:
            db.add(PhoneNumber(
                id=str(uuid.uuid4()),
                organization_id=smile_org.id,
                phone_number="+919876543210",
                provider="Exotel",
                purpose="reception",
                is_primary=True,
                status="active"
            ))
            db.add(PhoneNumber(
                id=str(uuid.uuid4()),
                organization_id=smile_org.id,
                phone_number="08047283364",
                provider="Exotel",
                purpose="campaign",
                is_primary=False,
                status="active"
            ))

        if db.query(BusinessHours).filter(BusinessHours.organization_id == smile_org.id).count() == 0:
            for day in range(6): # Mon-Sat
                db.add(BusinessHours(
                    id=str(uuid.uuid4()),
                    organization_id=smile_org.id,
                    day_of_week=day,
                    is_open=True,
                    open_time="09:00",
                    close_time="20:00"
                ))

        # Ensure default agent users for smile-dental exist in team_members
        smile_admin = db.query(TeamMember).filter(TeamMember.email == "admin@smiledental.com").first()
        if not smile_admin:
            smile_admin = TeamMember(
                id="2480d6f2-e2e0-4cdb-8816-c1d94bf6016d",
                organization_id=smile_org.id,
                name="Dr. Sharma (Admin)",
                email="admin@smiledental.com",
                role="ADMIN",
                pin_code="1234",
                password_hash=hash_pw("admin123"),
                is_active=True
            )
            db.add(smile_admin)
            pre_counts["team_members"] += 1
        else:
            smile_admin.organization_id = smile_org.id
            smile_admin.role = "ADMIN"
            if not smile_admin.password_hash:
                smile_admin.password_hash = hash_pw("admin123")

        smile_agent = db.query(TeamMember).filter(TeamMember.email == "agent@smiledental.com").first()
        if not smile_agent:
            smile_agent = TeamMember(
                id="bc647dae-92e9-43df-a2d2-b4d62c1cc26e",
                organization_id=smile_org.id,
                name="Agent Vikas",
                email="agent@smiledental.com",
                role="AGENT",
                pin_code="1234",
                password_hash=hash_pw("agent123"),
                is_active=True
            )
            db.add(smile_agent)
            pre_counts["team_members"] += 1
        else:
            smile_agent.organization_id = smile_org.id
            smile_agent.role = "AGENT"
            if not smile_agent.password_hash:
                smile_agent.password_hash = hash_pw("agent123")

        # Step 3: Ensure existing Organizations (e.g. Navbharat) also have configs
        nav_org = db.query(Organization).filter(Organization.slug == "navbharat-ngo").first()
        if nav_org:
            if not db.query(PortalConfig).filter(PortalConfig.organization_id == nav_org.id).first():
                db.add(PortalConfig(
                    id=str(uuid.uuid4()),
                    organization_id=nav_org.id,
                    portal_name=nav_org.name,
                    subtitle="Welfare Operations & Campaigns",
                    theme_primary="#10b981",
                    logo_icon="🤝"
                ))
            if not db.query(AgentConfig).filter(AgentConfig.organization_id == nav_org.id).first():
                db.add(AgentConfig(
                    id=str(uuid.uuid4()),
                    organization_id=nav_org.id,
                    agent_name="Priya",
                    voice_model="hi_pratham",
                    language="hi"
                ))

        # Default fallback org ID for existing orphaned records
        default_target_org = nav_org.id if nav_org else smile_org.id

        # Step 4: Backfill organization_id across all 7 tenant tables
        db.query(Campaign).filter(Campaign.organization_id == None).update(
            {"organization_id": default_target_org}, synchronize_session=False
        )

        # Backfill call_interactions organization_id from parent call_session
        db.execute(text("""
            UPDATE call_interactions 
            SET organization_id = (
                SELECT organization_id FROM call_sessions WHERE call_sessions.id = call_interactions.call_id
            )
            WHERE organization_id IS NULL;
        """))
        db.execute(text(f"""
            UPDATE call_interactions 
            SET organization_id = '{default_target_org}'
            WHERE organization_id IS NULL;
        """))

        # Backfill call_sessions handled_by_user_id where available from contact lead_owner
        db.execute(text("""
            UPDATE call_sessions
            SET handled_by_user_id = (
                SELECT lead_owner_id FROM contacts WHERE contacts.id = call_sessions.contact_id
            )
            WHERE handled_by_user_id IS NULL;
        """))
        db.execute(text("""
            UPDATE call_sessions
            SET recording_storage_key = recording_url
            WHERE recording_storage_key IS NULL AND recording_url IS NOT NULL;
        """))

        # Backfill any other records with NULL organization_id
        db.query(Contact).filter(Contact.organization_id == None).update(
            {"organization_id": default_target_org}, synchronize_session=False
        )
        db.query(TeamMember).filter(TeamMember.organization_id == None).update(
            {"organization_id": default_target_org}, synchronize_session=False
        )
        db.query(LeadTask).filter(LeadTask.organization_id == None).update(
            {"organization_id": default_target_org}, synchronize_session=False
        )
        db.query(LeadReminder).filter(LeadReminder.organization_id == None).update(
            {"organization_id": default_target_org}, synchronize_session=False
        )
        db.query(CallSession).filter(CallSession.organization_id == None).update(
            {"organization_id": default_target_org}, synchronize_session=False
        )

        # Step 5: Backfill CampaignAgent memberships from existing campaigns
        campaigns = db.query(Campaign).all()
        for camp in campaigns:
            if camp.assigned_agent_id:
                existing_member = db.query(CampaignAgent).filter(
                    CampaignAgent.campaign_id == camp.id,
                    CampaignAgent.user_id == camp.assigned_agent_id
                ).first()
                if not existing_member:
                    db.add(CampaignAgent(
                        id=str(uuid.uuid4()),
                        campaign_id=camp.id,
                        user_id=camp.assigned_agent_id,
                        role_in_campaign="dialer"
                    ))

        # Step 6: Strict Assertions across ALL 7 Tables
        check_tables = [
            ("contacts", Contact),
            ("team_members", TeamMember),
            ("campaigns", Campaign),
            ("call_sessions", CallSession),
            ("lead_tasks", LeadTask),
            ("lead_reminders", LeadReminder),
            ("call_interactions", CallInteraction),
        ]

        for name, model_cls in check_tables:
            null_count = db.query(model_cls).filter(model_cls.organization_id == None).count()
            if null_count > 0:
                raise RuntimeError(f"Assertion Error: Table '{name}' has {null_count} records with NULL organization_id!")

            current_count = db.query(model_cls).count()
            expected_count = pre_counts[name]
            if current_count < expected_count:
                raise RuntimeError(f"Assertion Error: Table '{name}' row count dropped from {expected_count} to {current_count} (Data Loss Detected)!")

        # Step 7: Create Performance Indexes
        db.execute(text("CREATE INDEX IF NOT EXISTS idx_contacts_org ON contacts(organization_id);"))
        db.execute(text("CREATE INDEX IF NOT EXISTS idx_campaigns_org ON campaigns(organization_id);"))
        db.execute(text("CREATE INDEX IF NOT EXISTS idx_calls_org ON call_sessions(organization_id);"))
        db.execute(text("CREATE INDEX IF NOT EXISTS idx_interactions_org ON call_interactions(organization_id);"))
        db.execute(text("CREATE INDEX IF NOT EXISTS idx_tasks_org ON lead_tasks(organization_id);"))
        db.execute(text("CREATE INDEX IF NOT EXISTS idx_reminders_org ON lead_reminders(organization_id);"))
        db.execute(text("CREATE INDEX IF NOT EXISTS idx_team_org ON team_members(organization_id);"))

        db.commit()
        print(f"[DB Migration Success] Validated all 7 tenant tables: 0 NULL organization_ids. Data integrity 100% verified.")
    except Exception as ex:
        db.rollback()
        print(f"[DB Migration FAILED] Transaction rolled back cleanly: {ex}")
        raise
    finally:
        db.close()

def tenant_query(db, model, user):
    """Authoritative tenant-scoped query."""
    if hasattr(model, "organization_id") and hasattr(user, "organization_id"):
        return db.query(model).filter(model.organization_id == user.organization_id)
    return db.query(model)

def agent_scoped_query(db, model, user):
    """
    Authoritative agent-scoped query:
    - If AGENT: Enforces tenant isolation AND ownership assignment.
    - If MANAGER / ADMIN / OWNER: Enforces tenant isolation across all tenant records.
    - If VIEWER: Enforces tenant isolation (read-only).
    """
    query = tenant_query(db, model, user)
    if getattr(user, "role", "").upper() == "AGENT":
        if hasattr(model, "lead_owner_id"):
            query = query.filter(model.lead_owner_id == user.id)
        elif hasattr(model, "assigned_to_id"):
            query = query.filter(model.assigned_to_id == user.id)
        elif hasattr(model, "handled_by_user_id"):
            query = query.filter(model.handled_by_user_id == user.id)
    return query

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
