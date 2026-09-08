"""
Path C PostgreSQL 18 CRM Service Layer
Manages Organizations, Contacts, Call Sessions, and Interaction Summaries.
"""

import os
import sys
import json
import uuid
import psycopg2
from psycopg2.extras import RealDictCursor, Json
from typing import Dict, Any, Optional

sys.stdout.reconfigure(encoding='utf-8')

PG_HOST = os.environ.get("POSTGRES_HOST", "127.0.0.1")
PG_PORT = int(os.environ.get("POSTGRES_PORT", "5432"))
PG_USER = os.environ.get("POSTGRES_USER", "postgres")
PG_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "")
PG_DB = os.environ.get("POSTGRES_DB", "voice_crm")

DEFAULT_ORG_SLUG = "mali-saini-ngo"

def get_connection():
    return psycopg2.connect(
        dbname=PG_DB,
        user=PG_USER,
        password=PG_PASSWORD,
        host=PG_HOST,
        port=PG_PORT,
        cursor_factory=RealDictCursor
    )


def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("CREATE EXTENSION IF NOT EXISTS \"pgcrypto\";")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS organizations (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        name TEXT NOT NULL,
        slug TEXT NOT NULL UNIQUE,
        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS contacts (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
        phone_number TEXT NOT NULL,
        name TEXT,
        email TEXT,
        status TEXT NOT NULL DEFAULT 'lead',
        preferred_language TEXT DEFAULT 'hi',
        last_called_at TIMESTAMPTZ,
        custom_fields JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT unique_org_phone UNIQUE (organization_id, phone_number)
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS call_sessions (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
        contact_id UUID REFERENCES contacts(id) ON DELETE SET NULL,
        provider TEXT NOT NULL,
        direction TEXT NOT NULL,
        from_number TEXT NOT NULL,
        to_number TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'initiated',
        started_at TIMESTAMPTZ,
        answered_at TIMESTAMPTZ,
        ended_at TIMESTAMPTZ,
        duration_s REAL DEFAULT 0,
        recording_url TEXT,
        transcript JSONB NOT NULL DEFAULT '[]'::jsonb,
        custom_fields JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS call_interactions (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        call_id UUID NOT NULL REFERENCES call_sessions(id) ON DELETE CASCADE,
        contact_id UUID REFERENCES contacts(id) ON DELETE SET NULL,
        intent_detected TEXT,
        confidence REAL,
        ai_summary TEXT,
        human_handoff_requested BOOLEAN DEFAULT FALSE,
        followup_required BOOLEAN DEFAULT FALSE,
        followup_date TIMESTAMPTZ,
        custom_fields JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # Default NGO Org
    cursor.execute("SELECT id FROM organizations WHERE slug = %s", (DEFAULT_ORG_SLUG,))
    org = cursor.fetchone()
    if not org:
        cursor.execute(
            "INSERT INTO organizations (name, slug) VALUES (%s, %s) RETURNING id",
            ("Mali Saini Samaj Seva Foundation", DEFAULT_ORG_SLUG)
        )
        print("[Path C DB] Created Default NGO Organization: Mali Saini Samaj Seva Foundation")

    conn.commit()
    conn.close()


def handle_call_start(call_id: str, from_number: str, to_number: str, direction: str = "inbound", provider: str = "plivo") -> Dict[str, Any]:
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM organizations WHERE slug = %s", (DEFAULT_ORG_SLUG,))
    org = cursor.fetchone()
    org_id = str(org['id'])

    cursor.execute("SELECT id FROM contacts WHERE organization_id = %s AND phone_number = %s", (org_id, from_number))
    contact = cursor.fetchone()

    if not contact:
        cursor.execute(
            "INSERT INTO contacts (organization_id, phone_number, status) VALUES (%s, %s, %s) RETURNING id",
            (org_id, from_number, "lead")
        )
        contact_id = str(cursor.fetchone()['id'])
    else:
        contact_id = str(contact['id'])

    try:
        valid_uuid = str(uuid.UUID(call_id))
    except Exception:
        valid_uuid = str(uuid.uuid4())

    cursor.execute(
        """
        INSERT INTO call_sessions 
        (id, organization_id, contact_id, provider, direction, from_number, to_number, status, started_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
        """,
        (valid_uuid, org_id, contact_id, provider, direction, from_number, to_number, "in_progress")
    )
    conn.commit()
    conn.close()
    return {"call_id": valid_uuid, "contact_id": contact_id, "org_id": org_id}


def handle_call_end(call_id: str, transcript_history: list, status: str = "completed", duration_s: float = 0.0) -> Dict[str, Any]:
    conn = get_connection()
    cursor = conn.cursor()

    try:
        valid_uuid = str(uuid.UUID(call_id))
    except Exception:
        cursor.execute("SELECT id FROM call_sessions ORDER BY created_at DESC LIMIT 1")
        row = cursor.fetchone()
        valid_uuid = str(row['id']) if row else str(uuid.uuid4())

    cursor.execute("SELECT organization_id, contact_id FROM call_sessions WHERE id = %s", (valid_uuid,))
    session = cursor.fetchone()
    if not session:
        conn.close()
        return {}

    contact_id = str(session['contact_id']) if session['contact_id'] else None

    cursor.execute(
        """
        UPDATE call_sessions 
        SET status = %s, duration_s = %s, transcript = %s, ended_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
        WHERE id = %s
        """,
        (status, duration_s, Json(transcript_history), valid_uuid)
    )

    transcript_text = " ".join([t.get("content", "") for t in transcript_history]).lower()
    intent = "general_information"
    human_handoff = False

    if "donation" in transcript_text or "डोनेशन" in transcript_text or "दान" in transcript_text:
        intent = "donation_inquiry"
    elif "tax" in transcript_text or "80g" in transcript_text or "रसीद" in transcript_text:
        intent = "tax_receipt"
    elif "manager" in transcript_text or "मैनेजर" in transcript_text or "person" in transcript_text:
        intent = "human_handoff"
        human_handoff = True

    summary = f"Caller inquired about {intent.replace('_', ' ')}. Plivo session completed successfully."

    cursor.execute(
        """
        INSERT INTO call_interactions
        (call_id, contact_id, intent_detected, confidence, ai_summary, human_handoff_requested, followup_required)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (valid_uuid, contact_id, intent, 0.95, summary, human_handoff, intent == "donation_inquiry")
    )

    conn.commit()
    conn.close()
    return {"call_id": valid_uuid, "intent": intent, "summary": summary}
