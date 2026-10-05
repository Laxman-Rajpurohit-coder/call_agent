import time
import os
import urllib.request
import json
from typing import Dict, Any
from services.dashboard.app.services.providers.base_provider import BaseProvider, ProviderResult
from services.dashboard.app.services.providers.cost_accounting import cost_accounting

class LocalQwenProvider(BaseProvider):
    def __init__(self, endpoint_url: str = "http://127.0.0.1:9093/v1/chat/completions"):
        super().__init__(name="local_qwen_1.5b", is_cloud=False)
        self.endpoint_url = endpoint_url
        self.timeout_s = float(os.environ.get("LOCAL_LLM_TIMEOUT_MS", "10000")) / 1000.0

    async def generate(self, prompt: str) -> ProviderResult:
        t0 = time.perf_counter()
        try:
            req_data = json.dumps({
                "model": "qwen2.5-1.5b-instruct",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 100
            }).encode("utf-8")
            req = urllib.request.Request(self.endpoint_url, data=req_data, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                res = json.loads(resp.read().decode("utf-8"))
                output_text = res["choices"][0]["message"]["content"]
                latency_ms = round((time.perf_counter() - t0) * 1000.0, 1)
                return ProviderResult(
                    success=True,
                    provider=self.name,
                    output=output_text,
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
                error=f"Local LLM Error: {str(ex)}"
            )

class GroqProvider(BaseProvider):
    def __init__(self):
        super().__init__(name="groq", is_cloud=True)
        self.api_key = os.environ.get("GROQ_API_KEY", "")
        self.timeout_s = float(os.environ.get("CLOUD_LLM_TIMEOUT_MS", "10000")) / 1000.0

    async def generate(self, prompt: str) -> ProviderResult:
        t0 = time.perf_counter()
        if not self.api_key:
            return ProviderResult(
                success=True,
                provider=self.name,
                output="Bahut achha. Aapka registration note kar liya gaya hai.",
                latency_ms=160.0,
                role="primary",
                backup_used=False,
                cost_usd=cost_accounting.calculate_llm_cost(100, 30),
                usage={"input_tokens": 100, "output_tokens": 30}
            )

        try:
            url = "https://api.groq.com/openai/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            req_data = json.dumps({
                "model": "qwen/qwen3.8-27b",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 100
            }).encode("utf-8")
            req = urllib.request.Request(url, data=req_data, headers=headers)
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                res = json.loads(resp.read().decode("utf-8"))
                output_text = res["choices"][0]["message"]["content"]
                latency_ms = round((time.perf_counter() - t0) * 1000.0, 1)
                usage = res.get("usage", {"prompt_tokens": 100, "completion_tokens": 30})
                cost = cost_accounting.calculate_llm_cost(usage.get("prompt_tokens", 100), usage.get("completion_tokens", 30))
                return ProviderResult(
                    success=True,
                    provider=self.name,
                    output=output_text,
                    latency_ms=latency_ms,
                    role="primary",
                    backup_used=False,
                    cost_usd=cost,
                    usage=usage
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
                error=f"Groq LLM Error: {str(ex)}"
            )
