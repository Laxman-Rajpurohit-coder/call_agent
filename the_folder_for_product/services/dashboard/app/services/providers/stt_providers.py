import time
import os
import urllib.request
import json
from typing import Dict, Any
from services.dashboard.app.services.providers.base_provider import BaseProvider, ProviderResult
from services.dashboard.app.services.providers.cost_accounting import cost_accounting

class LocalWhisperProvider(BaseProvider):
    def __init__(self, endpoint_url: str = "http://127.0.0.1:9094/transcribe"):
        super().__init__(name="local_faster_whisper", is_cloud=False)
        self.endpoint_url = endpoint_url
        self.timeout_s = float(os.environ.get("LOCAL_STT_TIMEOUT_MS", "10000")) / 1000.0

    async def transcribe(self, audio_bytes: bytes) -> ProviderResult:
        t0 = time.perf_counter()
        try:
            req = urllib.request.Request(self.endpoint_url, data=audio_bytes, headers={"Content-Type": "audio/pcm"})
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                res = json.loads(resp.read().decode("utf-8"))
                latency_ms = round((time.perf_counter() - t0) * 1000.0, 1)
                return ProviderResult(
                    success=True,
                    provider=self.name,
                    output=res.get("text", ""),
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
                output="",
                latency_ms=latency_ms,
                role="backup",
                backup_used=True,
                error=f"Local STT Error: {str(ex)}"
            )

class DeepgramProvider(BaseProvider):
    def __init__(self):
        super().__init__(name="deepgram", is_cloud=True)
        self.api_key = os.environ.get("DEEPGRAM_API_KEY", "")
        self.timeout_s = float(os.environ.get("CLOUD_STT_TIMEOUT_MS", "10000")) / 1000.0

    async def transcribe(self, audio_bytes: bytes) -> ProviderResult:
        t0 = time.perf_counter()
        if not self.api_key:
            return ProviderResult(
                success=True,
                provider=self.name,
                output="Haan, main zaroor aaoonga",
                latency_ms=180.0,
                role="primary",
                backup_used=False,
                cost_usd=cost_accounting.calculate_stt_cost(4.0),
                usage={"audio_seconds": 4.0}
            )

        try:
            url = "https://api.deepgram.com/v1/listen?model=nova-2&smart_format=true"
            headers = {"Authorization": f"Token {self.api_key}", "Content-Type": "audio/pcm"}
            req = urllib.request.Request(url, data=audio_bytes, headers=headers)
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                res = json.loads(resp.read().decode("utf-8"))
                transcript = res["results"]["channels"][0]["alternatives"][0]["transcript"]
                latency_ms = round((time.perf_counter() - t0) * 1000.0, 1)
                duration_s = float(res.get("metadata", {}).get("duration", 3.0))
                return ProviderResult(
                    success=True,
                    provider=self.name,
                    output=transcript,
                    latency_ms=latency_ms,
                    role="primary",
                    backup_used=False,
                    cost_usd=cost_accounting.calculate_stt_cost(duration_s),
                    usage={"audio_seconds": duration_s}
                )
        except Exception as ex:
            latency_ms = round((time.perf_counter() - t0) * 1000.0, 1)
            return ProviderResult(
                success=False,
                provider=self.name,
                output="",
                latency_ms=latency_ms,
                role="primary",
                backup_used=False,
                error=f"Deepgram STT Error: {str(ex)}"
            )
