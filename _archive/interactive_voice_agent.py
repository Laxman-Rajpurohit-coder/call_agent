import os
import sys
import time
import uuid
import wave
import json
import asyncio
import numpy as np
import sounddevice as sd
import httpx
from datetime import datetime

try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

ROOT_DIR = r"c:\daily_works\superfone_call"
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from services.dashboard.app.services.script_engine import ScriptEngine
from services.dashboard.app.database import SessionLocal
from services.dashboard.app.models import CallSession, CallInteraction, Contact, Organization

STT_URL = "http://127.0.0.1:9094/stt"
LLM_URL = "http://127.0.0.1:9093/llm"
TTS_URL = "http://127.0.0.1:9095/tts"

SAMPLE_RATE_MIC = 16000 # 16kHz float32 for Whisper STT
SILENCE_THRESHOLD = 0.015 # RMS Energy Threshold
SILENCE_DURATION = 1.2 # Seconds of silence to end turn
MIN_SPEECH_DURATION = 0.4 # Minimum speech length

def play_pcm_audio(audio_bytes, sample_rate=8000):
    """Play 16-bit PCM mono audio bytes live through speakers"""
    try:
        samples = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        sd.play(samples, samplerate=sample_rate)
        sd.wait()
    except Exception as ex:
        print(f"[Playback Error] {ex}")

async def synthesize_and_speak(text, voice="hi_pratham"):
    """Synthesize text via TTS Worker and play aloud"""
    print(f"\n🤖 AI AGENT: \"{text}\"")
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(TTS_URL, json={"text": text, "voice": voice}, timeout=10.0)
            if resp.status_code == 200:
                play_pcm_audio(resp.content, sample_rate=8000)
            else:
                print(f"[TTS Error] Status: {resp.status_code}")
        except Exception as e:
            print(f"[TTS Request Failed] {e}")

def record_user_speech():
    """Record live microphone input with Voice Activity Detection (VAD)"""
    print("\n🎙️ [AGENT IS LISTENING... SPEAK NOW INTO YOUR MICROPHONE]")
    audio_frames = []
    speaking = False
    silence_start = None
    speech_start_time = None

    def callback(indata, frames, time_info, status):
        nonlocal speaking, silence_start, speech_start_time
        rms = np.sqrt(np.mean(indata**2))
        
        if rms > SILENCE_THRESHOLD:
            if not speaking:
                speaking = True
                speech_start_time = time.time()
                print("   🔊 [Speech Detected - Recording...]")
            audio_frames.append(indata.copy())
            silence_start = None
        else:
            if speaking:
                audio_frames.append(indata.copy())
                if silence_start is None:
                    silence_start = time.time()

    with sd.InputStream(samplerate=SAMPLE_RATE_MIC, channels=1, dtype='float32', callback=callback):
        while True:
            sd.sleep(100)
            if speaking and silence_start and (time.time() - silence_start >= SILENCE_DURATION):
                print("   ⏹️ [End of Speech Detected - Processing...]")
                break
            # Maximum 15 second turn cap
            if speaking and speech_start_time and (time.time() - speech_start_time > 15.0):
                print("   ⏱️ [Max Turn Length Reached]")
                break

    if not audio_frames:
        return None

    full_audio = np.concatenate(audio_frames, axis=0)
    # Convert float32 16kHz mono to 16-bit PCM bytes
    pcm16 = (full_audio * 32767.0).astype(np.int16).tobytes()
    return pcm16

async def transcribe_audio(pcm16_bytes):
    """Send PCM16 audio bytes to STT Worker"""
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(STT_URL, content=pcm16_bytes, timeout=10.0)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("text", "").strip(), data.get("confidence", 0.95)
        except Exception as e:
            print(f"[STT Request Failed] {e}")
    return "", 0.0

async def start_interactive_call():
    print("=" * 70)
    print("  SUPERFONE AI VOICE PLATFORM — LIVE AGENT OUTBOUND CALL SESSION")
    print("=" * 70)
    print("📲 [SIMULATED PHONE RINGING... CALL ORIGINATING FROM AGENT]")
    time.sleep(1.5)
    print("📞 [CALL CONNECTED! AGENT INITIATING CONVERSATION...]")

    call_id = f"live_call_{uuid.uuid4().hex[:8]}"
    start_time = datetime.utcnow()
    user_phone = "+919876543210"

    # Vote Campaign Script Engine
    vote_script = {
        "version": 1,
        "steps": [
            {
                "id": "welcome",
                "type": "say",
                "text": "Namaste! Main Mali Saini Samaj Seva Foundation ki taraf se baat kar raha hoon."
            },
            {
                "id": "appeal",
                "type": "say",
                "text": "Samaj ke vikas, shiksha aur pragati ke liye, aagami chunav mein pratyashi Vikas Gahlot ji ko apna amulya vote dekar bhari bahumat se vijayi banayein."
            },
            {
                "id": "question",
                "type": "ask",
                "text": "Kya aap Vikas Gahlot ji ko apna vote aur samarthan denge?"
            },
            {
                "id": "intent",
                "type": "intent",
                "branches": {
                    "INTERESTED": "confirmation",
                    "NOT_INTERESTED": "closing",
                    "CALLBACK": "callback",
                    "HUMAN_HANDOFF": "handoff"
                }
            },
            {
                "id": "confirmation",
                "type": "say",
                "text": "Bahut bahut dhanyavaad! Aapka samarthan hamari taaqat hai. 10 September ko kram sankhya 1 par vote dekar vikas ko chunein. Dhanyavaad!"
            },
            {
                "id": "closing",
                "type": "say",
                "text": "Koi baat nahi ji. Aapka samay dene ke liye bahut bahut dhanyavaad. Aapka din shubh ho."
            },
            {
                "id": "callback",
                "type": "say",
                "text": "Ji bilkul, hum aapko shaam ko wapas call karenge. Dhanyavaad!"
            },
            {
                "id": "handoff",
                "type": "say",
                "text": "Main aapki call hamare chunav campaign manager ko transfer kar raha hoon. Kripya line par bane rahein."
            }
        ]
    }

    engine = ScriptEngine(vote_script)

    # 1. Agent Initiates Welcome Greeting
    welcome_text = "Namaste."
    await synthesize_and_speak(welcome_text)

    # 2. Record User Spoken Answer
    pcm_audio = record_user_speech()
    user_transcript = ""
    stt_conf = 0.95

    if pcm_audio:
        user_transcript, stt_conf = await transcribe_audio(pcm_audio)
        print(f"👤 YOU SPOKE: \"{user_transcript}\" (Confidence: {stt_conf:.2f})")
    else:
        print("👤 YOU SPOKE: [Silence / No audio captured]")

    if user_transcript:
        # 3. Classify Intent & Execute Agent Response
        intent = engine.classify_intent(user_transcript)
        print(f"\n🎯 INTENT CLASSIFIED: [{intent}]")

        if intent == "INTERESTED":
            reply_text = "Aapka samarthan aur ruchi ke liye bahut bahut dhanyavaad!"
        elif intent == "NOT_INTERESTED":
            reply_text = "Aapka samay dene ke liye bahut bahut dhanyavaad. Aapka din shubh ho."
        elif intent == "CALLBACK":
            reply_text = "Ji bilkul, hum aapko wapas call karenge. Dhanyavaad!"
        else:
            reply_text = "Main aapki call hamare manager ko transfer kar raha hoon."

    await synthesize_and_speak(reply_text)

    # 4. Save Call Session & Interaction in CRM DB
    end_time = datetime.utcnow()
    duration_s = round((end_time - start_time).total_seconds(), 1)

    db = SessionLocal()
    try:
        org = db.query(Organization).first()
        org_id = org.id if org else call_id

        session_rec = CallSession(
            id=call_id,
            organization_id=org_id,
            provider="live_mic_agent",
            direction="outbound",
            from_number="+918000000700",
            to_number=user_phone,
            status="completed",
            started_at=start_time,
            ended_at=end_time,
            duration_s=duration_s,
            transcript=[
                {"role": "assistant", "content": welcome_text},
                {"role": "user", "content": user_transcript},
                {"role": "assistant", "content": reply_text}
            ]
        )
        db.add(session_rec)

        interaction = CallInteraction(
            call_id=call_id,
            intent_detected=intent,
            confidence=stt_conf,
            ai_summary=f"Live Agent Call to {user_phone}. User spoke: '{user_transcript}'. Mapped Intent: '{intent}'."
        )
        db.add(interaction)
        db.commit()
        print(f"\n💾 [CALL SESSION SAVED TO CRM DATABASE! Call ID: {call_id}]")
        print("   You can refresh the 'Voice CRM & Calls' dashboard to view the transcript live!")

    except Exception as ex:
        print(f"[CRM Save Warning] {ex}")
    finally:
        db.close()

    print("\n=" * 70)
    print("  LIVE CALL SESSION COMPLETED SUCCESSFULLY!")
    print("=" * 70)

if __name__ == "__main__":
    asyncio.run(start_interactive_call())
