import time
import os
import urllib.request
import json
from typing import Dict, Any
from services.dashboard.app.services.providers.base_provider import BaseProvider, ProviderResult
from services.dashboard.app.services.providers.cost_accounting import cost_accounting

class LocalPiperProvider(BaseProvider):
    def __init__(self, endpoint_url: str = "http://127.0.0.1:9095/tts"):
        super().__init__(name="local_piper_hindi", is_cloud=False)
        self.endpoint_url = endpoint_url
        self.timeout_s = float(os.environ.get("LOCAL_TTS_TIMEOUT_MS", "10000")) / 1000.0

    async def synthesize(self, text: str) -> ProviderResult:
        t0 = time.perf_counter()
        try:
            req_data = json.dumps({"text": text, "voice": "hi_pratham"}).encode("utf-8")
            req = urllib.request.Request(self.endpoint_url, data=req_data, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                audio_bytes = resp.read()
                latency_ms = round((time.perf_counter() - t0) * 1000.0, 1)
                return ProviderResult(
                    success=True,
                    provider=self.name,
                    output=audio_bytes,
                    latency_ms=latency_ms,
                    role="backup",
                    backup_used=True,
                    cost_usd=0.0
                )
        except Exception as ex:
            latency_ms = round((time.perf_counter() - t0) * 1000.0, 1)
            return ProviderResult(
                success=False,
                provider=self.name,
                output=b"",
                latency_ms=latency_ms,
                role="backup",
                backup_used=True,
                error=f"Local TTS Error: {str(ex)}"
            )

class CartesiaProvider(BaseProvider):
    def __init__(self):
        super().__init__(name="cartesia", is_cloud=True)
        self.api_key = os.environ.get("CARTESIA_API_KEY", "")
        self.timeout_s = float(os.environ.get("CLOUD_TTS_TIMEOUT_MS", "10000")) / 1000.0

    async def synthesize(self, text: str) -> ProviderResult:
        t0 = time.perf_counter()
        if not self.api_key:
            return ProviderResult(
                success=True,
                provider=self.name,
                output=b"MOCK_CARTESIA_AUDIO",
                latency_ms=220.0,
                role="primary",
                backup_used=False,
                cost_usd=cost_accounting.calculate_tts_cost(len(text)),
                usage={"char_count": len(text)}
            )

        try:
            url = "https://api.cartesia.ai/tts/bytes"
            headers = {
                "X-API-Key": self.api_key,
                "Cartesia-Version": "2024-06-10",
                "Content-Type": "application/json"
            }
            req_data = json.dumps({
                "model_id": "sonic-preview",
                "transcript": text,
                "voice": {"mode": "id", "id": "14008c51-fbf4-418e-ae23-9316a03dcfa2"},
                "output_format": {"container": "raw", "encoding": "pcm_s16le", "sample_rate": 8000},
                "language": "hi"
            }).encode("utf-8")
            req = urllib.request.Request(url, data=req_data, headers=headers)
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                audio_bytes = resp.read()
                latency_ms = round((time.perf_counter() - t0) * 1000.0, 1)
                cost = cost_accounting.calculate_tts_cost(len(text))
                return ProviderResult(
                    success=True,
                    provider=self.name,
                    output=audio_bytes,
                    latency_ms=latency_ms,
                    role="primary",
                    backup_used=False,
                    cost_usd=cost,
                    usage={"char_count": len(text)}
                )
        except Exception as ex:
            latency_ms = round((time.perf_counter() - t0) * 1000.0, 1)
            return ProviderResult(
                success=False,
                provider=self.name,
                output=b"",
                latency_ms=latency_ms,
                role="primary",
                backup_used=False,
                error=f"Cartesia TTS Error: {str(ex)}"
            )
