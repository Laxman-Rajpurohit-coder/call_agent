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

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
