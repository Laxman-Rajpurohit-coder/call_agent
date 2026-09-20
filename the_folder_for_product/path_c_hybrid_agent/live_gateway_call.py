"""
Live Telephony AudioSocket Call Simulation against Port 9092
Streams caller audio (H4 Ayush, E4 Kabir, M3 Shreeraj) over socket and plays Pratham AI's
live responses (H1 Kavita, E1 Arushi, M1 Kavita) out loud in real time.
"""

import os
import sys
import time
import socket
import struct
import asyncio
import winsound
import tempfile
import wave

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from path_c_hybrid_agent.tts_cartesia import synthesize_speech_hd

SERVER_HOST = "127.0.0.1"
SERVER_PORT = 9092

LIVE_CALL_TURNS = [
    # Turn 1: Hindi
    {
        "turn": 1,
        "lang": "Hindi",
        "caller_speaker": "Rajesh Kumar (H4 Ayush Male)",
        "caller_voice_id": "791d5162-d5eb-40f0-8189-f19db44611d8",
        "caller_text": "नमस्ते! मैं माली सैनी समाज सेवा फाउंडेशन के बारे में जानना चाहता हूँ।"
    },
    # Turn 2: English / Hinglish
    {
        "turn": 2,
        "lang": "English",
        "caller_speaker": "Vikram Singh (E4 Kabir Male)",
        "caller_voice_id": "cb9c954d-bcaa-43ed-82bf-aeb5e88a3cb5",
        "caller_text": "I want to donate 1000 rupees and get an 80G tax exemption receipt."
    },
    # Turn 3: Marwadi
    {
        "turn": 3,
        "lang": "Marwadi",
        "caller_speaker": "Rathore Ji (M3 Shreeraj Male)",
        "caller_voice_id": "c7be5dde-c1e6-4ebe-9096-ddc4b4edb1cc",
        "caller_text": "घणो-घणो धन्यवाद सा, मेरा नाम राजेश कुमार है।"
    }
]


def play_pcm_out_loud(pcm_bytes: bytes, sample_rate: int = 8000):
    if not pcm_bytes:
        return
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = tmp.name

        with wave.open(tmp_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(pcm_bytes)

        winsound.PlaySound(tmp_path, winsound.SND_FILENAME)
        try:
            os.remove(tmp_path)
        except Exception:
            pass
    except Exception as e:
        print(f"[Playback Note] {e}")


async def run_live_call_simulation():
    print("=" * 80)
    print("  📞 LIVE AUDIOSOCKET TELEPHONY CALL SIMULATION (PORT 9092)")
    print("  Testing Gateway Pipeline: AudioSocket Stream -> STT -> Groq LLM -> Cartesia TTS -> PostgreSQL CRM")
    print("================================================================================\n")

    for item in LIVE_CALL_TURNS:
        turn = item["turn"]
        lang = item["lang"]
        c_speaker = item["caller_speaker"]
        c_voice = item["caller_voice_id"]
        c_text = item["caller_text"]

        print(f"\n--- [TURN {turn}: {lang}] ---")
        print(f"🗣️ {c_speaker}: \"{c_text}\"")

        # 1. Connect AudioSocket Client for Turn
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((SERVER_HOST, SERVER_PORT))

        # Send UUID Header (0x01)
        call_uuid = os.urandom(16)
        hdr = struct.pack("!BH", 0x01, 16)
        s.sendall(hdr + call_uuid)

        # 2. Synthesize 8kHz Telephony PCM for Caller
        caller_pcm_24k = await synthesize_speech_hd(c_text, voice_id=c_voice, sample_rate=24000)
        caller_pcm_8k = b""
        if caller_pcm_24k:
            import numpy as np
            audio_np = np.frombuffer(caller_pcm_24k, dtype=np.int16)
            downsampled = audio_np[::3]
            caller_pcm_8k = downsampled.tobytes()

        # Stream Caller PCM over AudioSocket in 320B frames
        if caller_pcm_8k:
            print("   Streaming caller audio to gateway...")
            for i in range(0, len(caller_pcm_8k), 320):
                chunk = caller_pcm_8k[i:i+320].ljust(320, b"\x00")
                frame_hdr = struct.pack("!BH", 0x10, 320)
                s.sendall(frame_hdr + chunk)
                await asyncio.sleep(0.015)

        # Give gateway time to process STT -> LLM -> TTS
        print("   Listening for Pratham AI live streaming response...")
        response_pcm = bytearray()
        s.settimeout(6.0)
        t_start = time.time()

        while time.time() - t_start < 6.0:
            try:
                rx_hdr = s.recv(3)
                if not rx_hdr or len(rx_hdr) < 3:
                    break
                p_type, p_len = struct.unpack("!BH", rx_hdr)
                payload = s.recv(p_len)
                if p_type == 0x10:
                    response_pcm.extend(payload)
            except socket.timeout:
                break
            except Exception as ex:
                break

        print(f"   Received {len(response_pcm)} bytes from Pratham AI!")
        if response_pcm:
            print("   🔊 Playing Pratham AI live response out loud...")
            play_pcm_out_loud(bytes(response_pcm), sample_rate=8000)

        # Send Hangup (0x00)
        try:
            hangup_hdr = struct.pack("!BH", 0x00, 0)
            s.sendall(hangup_hdr)
            s.close()
        except Exception:
            pass

        await asyncio.sleep(1.0)

    print("\n" + "=" * 80)
    print("  ✅ LIVE AUDIOSOCKET CALL SIMULATION COMPLETED SUCCESSFULLY!")
    print("================================================================================")

if __name__ == "__main__":
    asyncio.run(run_live_call_simulation())
