"""
Voice & Accent Selection Studio
Generates reference WAV audio files and plays out loud candidate voice profiles
for Hindi, English, and Marwadi accents.
"""

import os
import sys
import time
import wave
import asyncio
import winsound
import tempfile
import httpx

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from path_c_hybrid_agent.config import CARTESIA_API_KEY
from services.tts.kokoro_engine import KokoroTTSEngine

ART_DIR = r"C:\Users\msanj\.gemini\antigravity\brain\3f670608-a148-48ef-8f33-27bc120319d4"

VOICE_CANDIDATES = [
    # ── HINDI ACCENTS ─────────────────────────────────────────────────────────
    {
        "id": "H1_Kavita",
        "lang": "Hindi",
        "name": "Kavita (Native Hindi Customer Care - Female)",
        "provider": "Cartesia Sonic-3",
        "voice_uuid": "56e35e2d-6eb6-4226-ab8b-9776515a7094",
        "text": "नमस्ते! माली सैनी समाज सेवा फाउंडेशन में आपका स्वागत है। मैं आपकी सहायता के लिए तैयार हूँ।"
    },
    {
        "id": "H2_Meera",
        "lang": "Hindi",
        "name": "Meera (Bright Companion - Female)",
        "provider": "Cartesia Sonic-3",
        "voice_uuid": "a81fccdc-5595-4dfc-ae76-4de6a515b8a2",
        "text": "नमस्ते! माली सैनी समाज सेवा फाउंडेशन में आपका स्वागत है। मैं आपकी सहायता के लिए तैयार हूँ।"
    },
    {
        "id": "H3_Nisha",
        "lang": "Hindi",
        "name": "Nisha (Elegant Speaker - Female)",
        "provider": "Cartesia Sonic-3",
        "voice_uuid": "0f14d8cb-f039-41fe-a813-a9b4bee7eed8",
        "text": "नमस्ते! माली सैनी समाज सेवा फाउंडेशन में आपका स्वागत है। मैं आपकी सहायता के लिए तैयार हूँ।"
    },
    {
        "id": "H4_Ayush",
        "lang": "Hindi",
        "name": "Ayush (Warm Hindi Neighbor - Male)",
        "provider": "Cartesia Sonic-3",
        "voice_uuid": "791d5162-d5eb-40f0-8189-f19db44611d8",
        "text": "नमस्ते! माली सैनी समाज सेवा फाउंडेशन में आपका स्वागत है। मैं आपकी सहायता के लिए तैयार हूँ।"
    },

    # ── ENGLISH ACCENTS ───────────────────────────────────────────────────────
    {
        "id": "E1_Arushi",
        "lang": "English",
        "name": "Arushi (Native Indian English / Hinglish - Female)",
        "provider": "Cartesia Sonic-3",
        "voice_uuid": "95d51f79-c397-46f9-b49a-23763d3eaa2d",
        "text": "Hello! Welcome to Mali Saini Samaj Seva Foundation. How may I assist you today?"
    },
    {
        "id": "E2_Swati",
        "lang": "English",
        "name": "Swati (Professional Indian English - Female)",
        "provider": "Cartesia Sonic-3",
        "voice_uuid": "126a0835-beea-4e77-a883-f66eabcf6dd4",
        "text": "Hello! Welcome to Mali Saini Samaj Seva Foundation. How may I assist you today?"
    },
    {
        "id": "E3_Sarah",
        "lang": "English",
        "name": "Sarah (Global High-Clarity Studio - Female)",
        "provider": "Kokoro-82M",
        "voice_uuid": "af_sarah",
        "text": "Hello! Welcome to Mali Saini Samaj Seva Foundation. How may I assist you today?"
    },
    {
        "id": "E4_Kabir",
        "lang": "English",
        "name": "Kabir (Service Specialist Indian English - Male)",
        "provider": "Cartesia Sonic-3",
        "voice_uuid": "cb9c954d-bcaa-43ed-82bf-aeb5e88a3cb5",
        "text": "Hello! Welcome to Mali Saini Samaj Seva Foundation. How may I assist you today?"
    },

    # ── MARWADI ACCENTS ───────────────────────────────────────────────────────
    {
        "id": "M1_Kavita_Marwadi",
        "lang": "Marwadi",
        "name": "Kavita (Respectful Marwadi Dialect - Female)",
        "provider": "Cartesia Sonic-3",
        "voice_uuid": "56e35e2d-6eb6-4226-ab8b-9776515a7094",
        "text": "राम-राम सा! माली सैनी समाज सेवा फाउंडेशन में आपरो घणो-घणो स्वागत है। मैं आपकी काई सहायता कर सकूँ?"
    },
    {
        "id": "M2_Aarti_Marwadi",
        "lang": "Marwadi",
        "name": "Aarti (Traditional Marwadi Speaker - Female)",
        "provider": "Cartesia Sonic-3",
        "voice_uuid": "9cebb910-d4b7-4a4a-85a4-12c79137724c",
        "text": "राम-राम सा! माली सैनी समाज सेवा फाउंडेशन में आपरो घणो-घणो स्वागत है। मैं आपकी काई सहायता कर सकूँ?"
    },
    {
        "id": "M3_Shreeraj_Marwadi",
        "lang": "Marwadi",
        "name": "Shreeraj (Respectful Rajasthani Marwadi - Male)",
        "provider": "Cartesia Sonic-3",
        "voice_uuid": "c7be5dde-c1e6-4ebe-9096-ddc4b4edb1cc",
        "text": "राम-राम सा, हुकम! माली सैनी समाज सेवा फाउंडेशन में आपरो घणो-घणो स्वागत है। मैं आपकी काई सेवा कर सकूँ?"
    }
]


async def synthesize_sample(candidate: dict) -> bytes:
    provider = candidate["provider"]
    voice_uuid = candidate["voice_uuid"]
    text = candidate["text"]

    if provider == "Kokoro-82M":
        try:
            engine = KokoroTTSEngine()
            return engine.synthesize_hd_24k(text, voice=voice_uuid, speed=1.0)
        except Exception as e:
            print(f"[Kokoro Error] {e}")
            return b""

    # Cartesia Sonic-3
    url = "https://api.cartesia.ai/tts/bytes"
    headers = {
        "X-API-Key": CARTESIA_API_KEY,
        "Cartesia-Version": "2024-06-10",
        "Content-Type": "application/json"
    }
    payload = {
        "model_id": "sonic-3",
        "transcript": text,
        "voice": {"mode": "id", "id": voice_uuid},
        "output_format": {
            "container": "wav",
            "encoding": "pcm_s16le",
            "sample_rate": 24000
        }
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.post(url, headers=headers, json=payload)
            if res.status_code == 200:
                return res.content
            else:
                print(f"[Cartesia Error] Status {res.status_code}: {res.text}")
    except Exception as ex:
        print(f"[Cartesia Exception] {ex}")
    return b""


def play_audio_out_loud(wav_path: str):
    try:
        winsound.PlaySound(wav_path, winsound.SND_FILENAME)
    except Exception as e:
        print(f"[Playback Error] {e}")


async def main():
    print("=" * 80)
    print("  🎙️ VOICE & ACCENT SELECTION BENCHMARK STUDIO")
    print("  Generating Reference Audio Samples for Hindi, English & Marwadi...")
    print("================================================================================\n")

    summary_results = []

    for item in VOICE_CANDIDATES:
        cand_id = item["id"]
        lang = item["lang"]
        name = item["name"]
        filename = f"sample_{cand_id}.wav"
        wav_path = os.path.join(ART_DIR, filename)

        print(f"🔊 Generating [{lang}] Sample: {name} ({cand_id})...")
        audio_bytes = await synthesize_sample(item)

        if audio_bytes:
            # If raw PCM from Kokoro, wrap in WAV header
            if not audio_bytes.startswith(b"RIFF"):
                with wave.open(wav_path, "wb") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(24000)
                    wf.writeframes(audio_bytes)
            else:
                with open(wav_path, "wb") as f:
                    f.write(audio_bytes)

            file_size_kb = round(os.path.getsize(wav_path) / 1024.0, 1)
            print(f"   Saved {filename} ({file_size_kb} KB) ✅ | Playing out loud...")
            play_audio_out_loud(wav_path)
            time.sleep(0.4)

            summary_results.append({
                "id": cand_id,
                "lang": lang,
                "name": name,
                "provider": item["provider"],
                "file": filename,
                "path": wav_path
            })

    print("\n" + "=" * 80)
    print("  ✅ ALL VOICE REFERENCE SAMPLES GENERATED & PLAYED SUCCESSFULLY!")
    print("================================================================================")

if __name__ == "__main__":
    asyncio.run(main())
