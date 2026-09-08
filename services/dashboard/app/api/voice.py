import urllib.request
import json
from fastapi import APIRouter, Response, HTTPException, UploadFile, File
from services.dashboard.app.schemas import TTSRequest
from services.dashboard.app.config import settings

router = APIRouter(prefix="/voice", tags=["Voice Studio"])

@router.post("/synthesize")
async def synthesize_audio(req: TTSRequest):
    studio_url = f"{settings.AUDIO_STUDIO_URL}/api/synthesize"
    data = json.dumps({
        "text": req.text,
        "voice": req.voice,
        "speed": req.speed,
        "volume_gain_db": req.volume_gain_db,
        "fade_in_ms": req.fade_in_ms
    }).encode("utf-8")

    try:
        http_req = urllib.request.Request(studio_url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(http_req, timeout=10.0) as resp:
            content = resp.read()
            headers = {}
            for h in ["X-Duration-Sec", "X-Latency-MS", "X-RTF", "X-RMS-DBFS", "X-Peak"]:
                if resp.headers.get(h):
                    headers[h] = resp.headers.get(h)
            return Response(content=content, media_type="audio/wav", headers=headers)
    except Exception as ex:
        raise HTTPException(status_code=500, detail=f"Audio Studio service error: {str(ex)}")

@router.post("/transcribe")
async def transcribe_audio_file(file: UploadFile = File(...)):
    import time
    import os
    import httpx

    t0 = time.time()
    audio_bytes = await file.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Audio file is empty")

    text = ""
    stt_engine = "Unknown"
    confidence = 0.95

    # 1. Primary: Groq Whisper-Large-v3-Turbo Cloud STT (~200ms)
    groq_key = os.environ.get("GROQ_API_KEY", "")
    if groq_key:
        try:
            headers = {"Authorization": f"Bearer {groq_key}"}
            files = {"file": (file.filename or "speech.wav", audio_bytes, file.content_type or "audio/wav")}
            data_form = {"model": "whisper-large-v3-turbo", "response_format": "json"}
            async with httpx.AsyncClient() as client:
                g_res = await client.post(
                    "https://api.groq.com/openai/v1/audio/transcriptions",
                    headers=headers, files=files, data=data_form, timeout=3.5
                )
                if g_res.status_code == 200:
                    text = g_res.json().get("text", "").strip()
                    stt_engine = "Groq Whisper-Turbo (Cloud Primary)"
        except Exception as ex:
            print(f"[Voice API Groq STT Exception] {ex}")

    # 2. Secondary: Deepgram Nova-2 Cloud STT (~250ms)
    if not text:
        dg_key = os.environ.get("DEEPGRAM_API_KEY", "")
        if dg_key:
            try:
                async with httpx.AsyncClient() as client:
                    dg_res = await client.post(
                        "https://api.deepgram.com/v1/listen?model=nova-2&smart_format=true",
                        headers={"Authorization": f"Token {dg_key}", "Content-Type": file.content_type or "audio/wav"},
                        content=audio_bytes, timeout=3.5
                    )
                    if dg_res.status_code == 200:
                        text = dg_res.json()["results"]["channels"][0]["alternatives"][0]["transcript"].strip()
                        stt_engine = "Deepgram Nova-2 (Cloud Backup)"
            except Exception as ex:
                print(f"[Voice API Deepgram STT Exception] {ex}")

    # 3. Fallback: STT Microservice on Port 9094
    if not text:
        try:
            async with httpx.AsyncClient() as client:
                res = await client.post("http://127.0.0.1:9094/stt", content=audio_bytes, timeout=1.5)
                if res.status_code == 200:
                    data = res.json()
                    text = data.get("text", "").strip()
                    confidence = data.get("confidence", 0.96)
                    stt_engine = "STT Microservice (Port 9094)"
        except Exception as e:
            print(f"[Voice API STT Service Warning] {e}")

    latency_ms = round((time.time() - t0) * 1000.0, 1)

    return {
        "text": text or "[Unrecognized speech or silence]",
        "confidence": confidence,
        "latency_ms": latency_ms,
        "stt_engine": stt_engine,
        "audio_bytes": len(audio_bytes)
    }


