import os
from pathlib import Path

WORKSPACE_DIR = str(Path(__file__).resolve().parents[3])
LEGACY_DIR = r"c:\daily_works\superfone_call"

# Multi-Path .env Resolution (AGENTS.md Rule 4)
for env_candidate in (
    os.path.join(WORKSPACE_DIR, ".env"),
    os.path.join(LEGACY_DIR, ".env"),
    os.path.join(str(Path(__file__).parent), ".env"),
    os.path.join(str(Path(__file__).parent.parent), ".env"),
):
    if os.path.exists(env_candidate):
        try:
            with open(env_candidate, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and "=" in line and not line.startswith("#"):
                        k, v = line.split("=", 1)
                        k_clean = k.strip()
                        if k_clean not in os.environ:
                            os.environ[k_clean] = v.strip().strip('"').strip("'")
        except Exception:
            pass

def _resolve_first_existing(*rel_parts) -> str:
    for base in (WORKSPACE_DIR, LEGACY_DIR):
        target = os.path.join(base, *rel_parts)
        if os.path.exists(target):
            return target
    return os.path.join(WORKSPACE_DIR, *rel_parts)

class Settings:
    PROJECT_NAME: str = "Superfone AI Voice Operations & Campaign Platform"
    VERSION: str = "2.0.0"
    API_V1_STR: str = "/api/v1"
    
    PORT: int = 9090
    HOST: str = "0.0.0.0"
    
    # DB
    SQLITE_DB_PATH: str = _resolve_first_existing("voice_crm.db")
    DATABASE_URL: str = os.environ.get("DATABASE_URL", f"sqlite:///{SQLITE_DB_PATH}")
    
    # Microservice Endpoints
    CALL_GATEWAY_URL: str = os.environ.get("CALL_GATEWAY_URL", "http://127.0.0.1:9092")
    LLM_SERVER_URL: str = os.environ.get("LLM_SERVER_URL", "http://127.0.0.1:9093")
    STT_WORKER_URL: str = os.environ.get("STT_WORKER_URL", "http://127.0.0.1:9094")
    TTS_WORKER_URL: str = os.environ.get("TTS_WORKER_URL", "http://127.0.0.1:9095")
    AUDIO_STUDIO_URL: str = os.environ.get("AUDIO_STUDIO_URL", "http://127.0.0.1:9096")
    
    # Log File Path
    CALL_GATEWAY_LOG: str = _resolve_first_existing("call_gateway.log")
    
    # Evaluation & Load Test Paths
    EVAL_REPORTS_DIR: str = _resolve_first_existing("evaluation", "reports", "generated")
    LOAD_TESTS_DIR: str = WORKSPACE_DIR if os.path.exists(WORKSPACE_DIR) else LEGACY_DIR

settings = Settings()
