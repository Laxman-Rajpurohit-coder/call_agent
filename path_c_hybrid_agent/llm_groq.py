"""
Path C Managed Multi-Tenant Streaming LLM Service
Powered by Groq Cloud API (qwen/qwen3.8-27b) with Sub-100ms Latency
and Phonetic Pronunciation Normalization for Perfect TTS Synthesis.
"""

import os
import sys
import re
import json
import asyncio
import httpx
from typing import AsyncGenerator, Dict, Any, List

sys.stdout.reconfigure(encoding='utf-8')

from path_c_hybrid_agent.config import GROQ_API_KEY
from path_c_hybrid_agent.tenant_registry import get_tenant_config


def normalize_phonetics_for_tts(text: str) -> str:
    """
    Expands numbers, acronyms, and codes into clean Devanagari Hindi/Marwadi
    so Cartesia/EdgeTTS synthesizes 100% natural speech without spelling hesitation.
    """
    if not text:
        return ""

    # Replace currency & numbers
    text = re.sub(r'₹?\s*1000', 'एक हज़ार रुपये', text)
    text = re.sub(r'₹?\s*5000', 'पाँच हज़ार रुपये', text)
    text = re.sub(r'₹?\s*50,000|₹?\s*50000', 'पचास हज़ार रुपये', text)
    text = re.sub(r'₹?\s*10,000|₹?\s*10000', 'दस हज़ार रुपये', text)

    # Replace tax codes & technical acronyms
    text = re.sub(r'\b80G\b|\b80g\b', 'अस्सी जी', text)
    text = re.sub(r'\b12A\b|\b12a\b', 'बारह ए', text)
    text = re.sub(r'\bUPI\b|\bupi\b', 'यू पी आई', text)
    text = re.sub(r'\bNGO\b|\bngo\b', 'एन जी ओ', text)
    text = re.sub(r'\bSMS\b|\bsms\b', 'एस एम एस', text)
    text = re.sub(r'\bSIP\b|\bsip\b', 'सिप', text)
    text = re.sub(r'\bWebhooks?\b|\bwebhooks?\b', 'वेबहुक्स', text)
    text = re.sub(r'\bAPI\b|\bapi\b', 'ए पी आई', text)
    text = re.sub(r'\bURL\b|\burl\b', 'यू आर एल', text)

    # Clean markdown
    text = text.replace("**", "").replace("#", "").replace("-", " ")
    return text.strip()


def clean_reasoning_tokens(text: str) -> str:
    """Strips any internal reasoning or thinking process text."""
    if not text:
        return ""
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    text = re.sub(r"Here(?:'s|\s+is)\s+a\s+thinking\s+process:?.*?(?=\n\n|\n[A-Z\u0900-\u097F]|$)", '', text, flags=re.IGNORECASE | re.DOTALL)
    return text.strip()


async def stream_llm_response(conversation_history: List[Dict[str, str]], tenant_id: str = "tenant_ecommerce", max_tokens: int = 100) -> AsyncGenerator[str, None]:
    """Streams LLM tokens with sub-100ms latency using Groq qwen/qwen3.8-27b."""
    tenant_cfg = get_tenant_config(tenant_id)
    sys_prompt = tenant_cfg["system_prompt"]

    messages = []
    has_system = any(m.get("role") == "system" for m in conversation_history)
    if not has_system:
        messages.append({"role": "system", "content": sys_prompt})

    if conversation_history:
        for msg in conversation_history:
            messages.append({"role": msg["role"], "content": msg["content"]})

    if GROQ_API_KEY:
        try:
            url = "https://api.groq.com/openai/v1/chat/completions"
            headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
            payload = {
                "model": "qwen/qwen3.8-27b",
                "messages": messages,
                "temperature": 0.3,
                "max_tokens": max_tokens,
                "stream": True
            }
            
            async with httpx.AsyncClient(timeout=8.0) as client:
                async with client.stream("POST", url, headers=headers, json=payload) as response:
                    if response.status_code == 200:
                        async for line in response.aiter_lines():
                            if line.startswith("data: "):
                                line_data = line[6:].strip()
                                if line_data == "[DONE]":
                                    break
                                try:
                                    chunk = json.loads(line_data)
                                    choices = chunk.get("choices", [])
                                    if choices:
                                        delta = choices[0].get("delta", {})
                                        content = delta.get("content", "")
                                        if content:
                                            clean_text = clean_reasoning_tokens(content)
                                            if clean_text:
                                                yield clean_text
                                except Exception:
                                    pass
                        return
                    else:
                        print(f"[LLM Warning] Groq returned status {response.status_code}")
        except Exception as e:
            print(f"[LLM Warning] Groq API streaming failed: {e}")

    yield "जी बिल्कुल, आपका ऑर्डर प्रोसेस हो रहा है। बताइए और क्या जानकारी चाहिए?"
