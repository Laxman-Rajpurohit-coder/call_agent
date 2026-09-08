"""
Path C Streaming LLM Service
Supports Groq API (Llama 3.1 8B Instant) and OpenAI API (GPT-4o-mini).
Falls back to local Qwen LLM server (port 9093) if external APIs fail.
"""

import os
import sys
import json
import asyncio
import httpx
from typing import AsyncGenerator, Dict, Any, List

sys.stdout.reconfigure(encoding='utf-8')

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

SYSTEM_PROMPT = (
    "You are Pratham, a warm, genuine, and friendly AI representative of Mali Saini Samaj Seva Foundation (an NGO).\n"
    "GOAL & RESPONSIBILITIES:\n"
    "1. Donation Assistance: Help callers with donation inquiries, explain donation options (UPI, Netbanking, Cards), and confirm 80G tax exemption receipts.\n"
    "2. Conversational Style: Speak authentically and warmly like a friendly coordinator on a phone call. Keep replies to 1-2 natural spoken sentences (around 12-20 words, under 3 seconds of speech).\n"
    "3. Language Policy: Match the caller's language. If the caller speaks Hindi or Hinglish, respond strictly in warm conversational Hindi using Devanagari script (e.g. 'जी बिल्कुल, आप UPI या नेटबैंकिंग से डोनेशन दे सकते हैं और 80G टैक्स रसीद भी मिलेगी।'). If the caller speaks English, respond in clear warm English.\n"
    "4. Human Handoff: If the caller explicitly asks to speak to a person or manager, politely agree and say 'जी, मैं तुरंत आपकी कॉल हमारे मैनेजर से कनेक्ट कर रहा हूँ।'\n"
    "5. Direct & Grounded: Only provide factual information. If information is unavailable, offer human assistance."
)


async def stream_llm_response(transcript: str, conversation_history: List[Dict[str, str]] = None) -> AsyncGenerator[str, None]:
    """Streams LLM tokens using Groq / OpenAI / Local Qwen fallback."""
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if conversation_history:
        for msg in conversation_history[-6:]:
            messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": transcript})

    # 1. Groq Streaming API
    if GROQ_API_KEY:
        try:
            url = "https://api.groq.com/openai/v1/chat/completions"
            headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
            payload = {"model": "llama-3.1-8b-instant", "messages": messages, "temperature": 0.3, "stream": True}
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                async with client.stream("POST", url, headers=headers, json=payload) as response:
                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            line_data = line[6:].strip()
                            if line_data == "[DONE]":
                                break
                            try:
                                chunk = json.loads(line_data)
                                content = chunk["choices"][0]["delta"].get("content", "")
                                if content:
                                    yield content
                            except Exception:
                                pass
            return
        except Exception as e:
            print(f"[LLM Warning] Groq API streaming failed: {e}. Falling back to local LLM.")

    # 2. Local Fallback to Qwen (Port 9093)
    try:
        url = "http://127.0.0.1:9093/llm/stream"
        payload = {"job": {"call_id": "hybrid_call", "transcript": transcript, "conversation_history": conversation_history or []}}
        async with httpx.AsyncClient(timeout=10.0) as client:
            async with client.stream("POST", url, json=payload) as response:
                async for line in response.aiter_lines():
                    if line:
                        try:
                            data = json.loads(line)
                            if data.get("type") == "token":
                                yield data.get("text", "")
                        except Exception:
                            pass
    except Exception as local_e:
        print(f"[LLM Error] Local LLM server unavailable: {local_e}")
        yield "जी बिल्कुल, Mali Saini Samaj Seva Foundation में डोनेशन देने के लिए धन्यवाद।"
