"""
Path C Streaming TTS Service
Supports Cartesia Sonic Streaming TTS API (hyper-realistic human voice).
Falls back to local Piper TTS worker (port 9095) if CARTESIA_API_KEY is missing.
"""

import os
import sys
import json
import asyncio
import httpx
from typing import Dict, Any

sys.stdout.reconfigure(encoding='utf-8')

CARTESIA_API_KEY = os.environ.get("CARTESIA_API_KEY", "")

async def synthesize_speech(text: str, voice_id: str = "hindi_female_sonic") -> bytes:
    """
    Synthesizes speech using Cartesia Sonic API (8000Hz PCM 16-bit mono).
    Falls back to local Piper TTS worker (port 9095) if API is unavailable.
    """
    if CARTESIA_API_KEY:
        url = "https://api.cartesia.ai/tts/bytes"
        headers = {
            "X-API-Key": CARTESIA_API_KEY,
            "Cartesia-Version": "2024-06-10",
            "Content-Type": "application/json"
        }
        payload = {
            "model_id": "sonic-multilingual",
            "transcript": text,
            "voice": {"mode": "id", "id": voice_id},
            "output_format": {
                "container": "raw",
                "encoding": "pcm_s16le",
                "sample_rate": 8000
            }
        }
        try:
            async with httpx.AsyncClient(timeout=6.0) as client:
                res = await client.post(url, headers=headers, json=payload)
                if res.status_code == 200:
                    return res.content
        except Exception as e:
            print(f"[TTS Warning] Cartesia API failed: {e}. Falling back to local TTS.")

    # Local Fallback to Piper (Port 9095)
    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            res = await client.post("http://127.0.0.1:9095/tts", json={"text": text})
            if res.status_code == 200:
                return res.content
    except Exception as local_e:
        print(f"[TTS Error] Local Piper TTS server unavailable: {local_e}")

    return b""
