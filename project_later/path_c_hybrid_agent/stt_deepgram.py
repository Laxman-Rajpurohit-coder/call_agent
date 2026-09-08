"""
Path C Streaming STT Service
Supports Deepgram Nova-2 WebSocket/HTTP streaming API with automatic local Faster-Whisper fallback.
"""

import os
import sys
import json
import asyncio
import httpx
from typing import Optional, Dict, Any

sys.stdout.reconfigure(encoding='utf-8')

DEEPGRAM_API_KEY = os.environ.get("DEEPGRAM_API_KEY", "")

async def transcribe_audio_chunk(pcm_bytes: bytes, sample_rate: int = 8000, language: str = "hi") -> Dict[str, Any]:
    """
    Transcribes audio using Deepgram Nova-2 HTTP/Streaming API.
    Falls back to local Faster-Whisper worker (port 9094) if DEEPGRAM_API_KEY is not set or network fails.
    """
    if DEEPGRAM_API_KEY:
        url = f"https://api.deepgram.com/v1/listen?model=nova-2-general&language={language}&encoding=linear16&sample_rate={sample_rate}&channels=1"
        headers = {
            "Authorization": f"Token {DEEPGRAM_API_KEY}",
            "Content-Type": "audio/raw"
        }
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.post(url, headers=headers, content=pcm_bytes)
                if res.status_code == 200:
                    data = res.json()
                    transcript = data["results"]["channels"][0]["alternatives"][0]["transcript"]
                    confidence = data["results"]["channels"][0]["alternatives"][0]["confidence"]
                    return {
                        "text": transcript.strip(),
                        "confidence": confidence,
                        "provider": "deepgram_nova2"
                    }
        except Exception as e:
            print(f"[STT Warning] Deepgram API call failed: {e}. Falling back to local STT.")

    # Local Fallback to Faster-Whisper (Port 9094)
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            files = {'file': ('audio.pcm', pcm_bytes, 'application/octet-stream')}
            res = await client.post("http://127.0.0.1:9094/stt", files=files)
            if res.status_code == 200:
                data = res.json()
                return {
                    "text": data.get("text", "").strip(),
                    "confidence": data.get("confidence", 0.90),
                    "provider": "local_faster_whisper"
                }
    except Exception as local_e:
        print(f"[STT Error] Local STT worker unavailable: {local_e}")

    return {"text": "", "confidence": 0.0, "provider": "none"}
