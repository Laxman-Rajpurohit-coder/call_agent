"""
Path C Hybrid Voice Agent Configuration
Stores API Keys & Connection Endpoints for Plivo, Deepgram, Groq, Cartesia, and PostgreSQL 18.
"""

import os

# Telephony Gateway
GATEWAY_HOST = os.environ.get("GATEWAY_HOST", "0.0.0.0")
GATEWAY_PORT = int(os.environ.get("GATEWAY_PORT", "9092"))

# PostgreSQL 18 CRM Database
POSTGRES_HOST = os.environ.get("POSTGRES_HOST", "127.0.0.1")
POSTGRES_PORT = int(os.environ.get("POSTGRES_PORT", "5432"))
POSTGRES_USER = os.environ.get("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "")
POSTGRES_DB = os.environ.get("POSTGRES_DB", "voice_crm")

# API Keys (Loaded from env)
DEEPGRAM_API_KEY = os.environ.get("DEEPGRAM_API_KEY", "")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
CARTESIA_API_KEY = os.environ.get("CARTESIA_API_KEY", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

# Default NGO Information
NGO_NAME = "Mali Saini Samaj Seva Foundation"
DEFAULT_ORG_SLUG = "mali-saini-ngo"
