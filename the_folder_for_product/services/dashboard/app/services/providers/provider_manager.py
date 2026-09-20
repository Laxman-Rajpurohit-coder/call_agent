import asyncio
from typing import Dict, Any, Tuple
from services.dashboard.app.services.providers.base_provider import ProviderResult
from services.dashboard.app.services.providers.circuit_breaker import CircuitBreaker
from services.dashboard.app.services.providers.stt_providers import LocalWhisperProvider, DeepgramProvider
from services.dashboard.app.services.providers.llm_providers import LocalQwenProvider, GroqProvider
from services.dashboard.app.services.providers.tts_providers import LocalPiperProvider, CartesiaProvider

class ProviderManager:
    """
    Cloud Primary -> Local Backup Engine Orchestrator
    1. STT : Deepgram (Cloud Primary)  -> Faster-Whisper (Local Backup)
    2. LLM : Groq LPU (Cloud Primary) -> Local Qwen GGUF (Local Backup)
    3. TTS : Cartesia (Cloud Primary)  -> Local Piper/Kokoro (Local Backup)
    """
    def __init__(self):
        # STT
        self.stt_primary = DeepgramProvider()
        self.stt_backup = LocalWhisperProvider()
        self.stt_breaker = CircuitBreaker("STT_Primary")

        # LLM
        self.llm_primary = GroqProvider()
        self.llm_backup = LocalQwenProvider()
        self.llm_breaker = CircuitBreaker("LLM_Primary")

        # TTS
        self.tts_primary = CartesiaProvider()
        self.tts_backup = LocalPiperProvider()
        self.tts_breaker = CircuitBreaker("TTS_Primary")

    async def transcribe(self, audio_bytes: bytes) -> ProviderResult:
        # 1. Try Cloud Primary STT (Deepgram)
        res = await self.stt_primary.transcribe(audio_bytes)
        if res.success:
            res.role = "primary"
            res.backup_used = False
            self.stt_breaker.record_success()
            return res

        # Cloud Primary Failed - Record failure & Fallback to Local Backup Engine
        self.stt_breaker.record_failure(is_qualifying=True)
        backup_reason = "PRIMARY_TIMEOUT" if "timeout" in (res.error or "").lower() else "PRIMARY_UNAVAILABLE"

        # 2. Invoke Local Backup STT (Faster-Whisper)
        backup_res = await self.stt_backup.transcribe(audio_bytes)
        backup_res.role = "backup"
        backup_res.backup_used = True
        backup_res.backup_reason = backup_reason
        return backup_res

    async def generate_response(self, prompt: str) -> ProviderResult:
        # 1. Try Cloud Primary LLM (Groq)
        res = await self.llm_primary.generate(prompt)
        if res.success:
            res.role = "primary"
            res.backup_used = False
            self.llm_breaker.record_success()
            return res

        self.llm_breaker.record_failure(is_qualifying=True)
        backup_reason = "PRIMARY_TIMEOUT" if "timeout" in (res.error or "").lower() else "PRIMARY_UNAVAILABLE"

        # 2. Invoke Local Backup LLM (Local Qwen GGUF)
        backup_res = await self.llm_backup.generate(prompt)
        backup_res.role = "backup"
        backup_res.backup_used = True
        backup_res.backup_reason = backup_reason
        return backup_res

    async def synthesize(self, text: str) -> ProviderResult:
        # 1. Try Cloud Primary TTS (Cartesia)
        res = await self.tts_primary.synthesize(text)
        if res.success:
            res.role = "primary"
            res.backup_used = False
            self.tts_breaker.record_success()
            return res

        self.tts_breaker.record_failure(is_qualifying=True)
        backup_reason = "PRIMARY_TIMEOUT" if "timeout" in (res.error or "").lower() else "PRIMARY_UNAVAILABLE"

        # 2. Invoke Local Backup TTS (Local Piper / Kokoro)
        backup_res = await self.tts_backup.synthesize(text)
        backup_res.role = "backup"
        backup_res.backup_used = True
        backup_res.backup_reason = backup_reason
        return backup_res

provider_manager = ProviderManager()
