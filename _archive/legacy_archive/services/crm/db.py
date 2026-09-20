"""
Tenant-Aware Database Layer for Voice CRM
Target Engine: PostgreSQL 18

Schema:
- organizations (id UUID, name TEXT, slug TEXT UNIQUE, created_at TIMESTAMPTZ)
- contacts (id UUID, organization_id UUID, phone_number TEXT, name TEXT, email TEXT, status TEXT, preferred_language TEXT, custom_fields JSONB, UNIQUE(organization_id, phone_number))
- call_sessions (id UUID, organization_id UUID, contact_id UUID, provider TEXT, direction TEXT, from_number TEXT, to_number TEXT, status TEXT, duration_s REAL, transcript JSONB, custom_fields JSONB)
- call_interactions (id UUID, call_id UUID, contact_id UUID, intent_detected TEXT, confidence REAL, ai_summary TEXT, human_handoff_requested BOOLEAN, followup_required BOOLEAN, custom_fields JSONB)
"""

import os
import sys
import json
import psycopg2
from psycopg2.extras import RealDictCursor
from typing import Dict, Any, List, Optional
import uuid

sys.stdout.reconfigure(encoding='utf-8')

PG_HOST = os.environ.get("POSTGRES_HOST", "127.0.0.1")
PG_PORT = int(os.environ.get("POSTGRES_PORT", "5432"))
PG_USER = os.environ.get("POSTGRES_USER", "postgres")
PG_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "")
PG_DB = os.environ.get("POSTGRES_DB", "voice_crm")


def get_connection():
    conn = psycopg2.connect(
        dbname=PG_DB,
        user=PG_USER,
        password=PG_PASSWORD,
        host=PG_HOST,
        port=PG_PORT,
        cursor_factory=RealDictCursor
    )
    return conn


def init_db():
    """Apply PostgreSQL 18 tenant-aware migrations."""
    conn = get_connection()
    cursor = conn.cursor()

    # Enable pgcrypto / gen_random_uuid extension
    cursor.execute("CREATE EXTENSION IF NOT EXISTS \"pgcrypto\";")

    # 1. Organizations
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS organizations (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        name TEXT NOT NULL,
        slug TEXT NOT NULL UNIQUE,
        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # 2. Contacts (Composite Unique: organization_id + phone_number)
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

    # 3. Call Sessions
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

    # 4. Call Interactions
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

    # Seed Default NGO Organization if not present
    cursor.execute("SELECT id FROM organizations WHERE slug = 'mali-saini-ngo'")
    org = cursor.fetchone()
    if not org:
        cursor.execute(
            "INSERT INTO organizations (name, slug) VALUES (%s, %s) RETURNING id",
            ("Mali Saini Samaj Seva Foundation", "mali-saini-ngo")
        )
        default_org_id = cursor.fetchone()['id']
        print(f"[PostgreSQL Migration] Created Default NGO Organization ID: {default_org_id}")

    conn.commit()
    conn.close()
    print("[PostgreSQL Migration] PostgreSQL 18 tenant-aware schema migration applied successfully.")


def print_schema_summary():
    """Inspect and print PostgreSQL table column attributes (psql \\d equivalent)."""
    conn = get_connection()
    cursor = conn.cursor()
    
    tables = ["organizations", "contacts", "call_sessions", "call_interactions"]
    print("\n" + "=" * 80)
    print("  POSTGRESQL 18 DATABASE SCHEMA INSPECTION SUMMARY (psql \\d REPRESENTATION)")
    print("=" * 80)

    for tbl in tables:
        cursor.execute("""
            SELECT 
                column_name, 
                data_type, 
                is_nullable, 
                column_default
            FROM information_schema.columns
            WHERE table_name = %s
            ORDER BY ordinal_position;
        """, (tbl,))
        cols = cursor.fetchall()

        cursor.execute("""
            SELECT tc.constraint_name, tc.constraint_type
            FROM information_schema.table_constraints tc
            WHERE tc.table_name = %s;
        """, (tbl,))
        constraints = cursor.fetchall()

        print(f"\n📋 PostgreSQL Table: \\d {tbl}")
        print("-" * 80)
        print(f"{'COLUMN':<24} | {'TYPE':<16} | {'NULLABLE':<8} | {'DEFAULT':<25}")
        print("-" * 80)
        for col in cols:
            dflt = str(col['column_default']) if col['column_default'] is not None else 'NULL'
            print(f"{col['column_name']:<24} | {col['data_type']:<16} | {col['is_nullable']:<8} | {dflt:<25}")
        
        if constraints:
            print("  Constraints / Indexes:")
            for con in constraints:
                print(f"    - {con['constraint_name']} ({con['constraint_type']})")

    conn.close()
    print("=" * 80)


if __name__ == "__main__":
    init_db()
    print_schema_summary()
