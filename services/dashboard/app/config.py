import os

class Settings:
    PROJECT_NAME: str = "Superfone AI Voice Operations & Campaign Platform"
    VERSION: str = "2.0.0"
    API_V1_STR: str = "/api/v1"
    
    PORT: int = 9090
    HOST: str = "0.0.0.0"
    
    # DB
    SQLITE_DB_PATH: str = r"c:\daily_works\superfone_call\voice_crm.db"
    DATABASE_URL: str = os.environ.get("DATABASE_URL", f"sqlite:///{SQLITE_DB_PATH}")
    
    # Microservice Endpoints
    CALL_GATEWAY_URL: str = os.environ.get("CALL_GATEWAY_URL", "http://127.0.0.1:9092")
    LLM_SERVER_URL: str = os.environ.get("LLM_SERVER_URL", "http://127.0.0.1:9093")
    STT_WORKER_URL: str = os.environ.get("STT_WORKER_URL", "http://127.0.0.1:9094")
    TTS_WORKER_URL: str = os.environ.get("TTS_WORKER_URL", "http://127.0.0.1:9095")
    AUDIO_STUDIO_URL: str = os.environ.get("AUDIO_STUDIO_URL", "http://127.0.0.1:9096")
    
    # Log File Path
    CALL_GATEWAY_LOG: str = r"c:\daily_works\superfone_call\call_gateway.log"
    
    # Evaluation & Load Test Paths
    EVAL_REPORTS_DIR: str = r"c:\daily_works\superfone_call\evaluation\reports\generated"
    LOAD_TESTS_DIR: str = r"c:\daily_works\superfone_call"

settings = Settings()
