import os
import sys
import json
import time
import struct
import wave
import asyncio
import uuid
import numpy as np
from scipy.signal import resample_poly

try:
    import winsound
    HAS_WINSOUND = True
except ImportError:
    HAS_WINSOUND = False

sys.path.insert(0, os.path.abspath("."))
sys.path.insert(0, os.path.abspath("dograh-evaluation/tools"))

from crm_bridge import get_records

SIMULATION_SCRIPT = [
    {
        "role": "Customer (Bot A)",
        "lang": "en",
        "text": "Hello, good morning! Is this the Malisaini Samaj Seva Foundation?"
    },
    {
        "role": "Customer (Bot A)",
        "lang": "hi",
        "text": "बालोतरा कार्यालय का समय और पता क्या है?"
    },
    {
        "role": "Customer (Bot A)",
        "lang": "en",
        "text": "Can you please schedule a callback for me with Director Sanjay Gahlot?"
    },
    {
        "role": "Customer (Bot A)",
        "lang": "en",
        "text": "Thank you, that was very helpful. Goodbye!"
    }
]

def synthesize_caller_speech(text: str, lang: str = "en") -> bytes:
    import subprocess
    piper_exe = r"c:\daily_works\superfone_call\piper\piper\piper.exe"
    if lang == "hi":
        model_onnx = r"c:\daily_works\superfone_call\models\hi_IN-pratham-medium.onnx"
    else:
        model_onnx = r"c:\daily_works\superfone_call\models\en_US-lessac-medium.onnx"

    cmd = [piper_exe, "--model", model_onnx, "--output-raw"]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    raw_22k, _ = proc.communicate(input=text.encode("utf-8"))
    if not raw_22k:
        return b"\x00\x00" * 8000
    samples_22k = np.frombuffer(raw_22k, dtype=np.int16)
    samples_8k = resample_poly(samples_22k, 160, 441).astype(np.int16)
    return samples_8k.tobytes()

def play_speaker(pcm_bytes: bytes):
    if HAS_WINSOUND:
        temp_wav = "temp_supervisor_stream.wav"
        with wave.open(temp_wav, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(8000)
            wf.writeframes(pcm_bytes)
        try:
            winsound.PlaySound(temp_wav, winsound.SND_FILENAME)
        except Exception:
            pass
        if os.path.exists(temp_wav):
            try: os.remove(temp_wav)
            except Exception: pass

async def run_live_bot_to_bot_simulation(host: str = "127.0.0.1", port: int = 9092):
    call_uuid = uuid.uuid4()
    print("\n" + "=" * 75)
    print("  LIVE BOT-TO-BOT TELEPHONY CONVERSATION SIMULATION")
    print(f"  Supervisor Monitoring Mode | Session: {call_uuid}")
    print(f"  Target Gateway: {host}:{port}")
    print("=" * 75 + "\n")

    try:
        reader, writer = await asyncio.open_connection(host, port)
    except Exception as ex:
        print(f"[ERROR] Could not connect to Call Gateway at {host}:{port} ({ex})")
        print("Please ensure .\\start_all.bat is running.")
        return

    # Send AudioSocket Handshake (UUID)
    uuid_bytes = call_uuid.bytes
    writer.write(struct.pack("!BH", 0x01, len(uuid_bytes)) + uuid_bytes)
    await writer.drain()

    # Background audio receiver from Receptionist Bot (Port 9092)
    incoming_ai_chunks = []
    stop_event = asyncio.Event()

    async def receive_ai_playback():
        while not stop_event.is_set():
            try:
                hdr = await asyncio.wait_for(reader.readexactly(3), timeout=0.2)
                p_type, p_len = struct.unpack("!BH", hdr)
                payload = await reader.readexactly(p_len)
                if p_type == 0x10 and payload:
                    incoming_ai_chunks.append(payload)
                elif p_type == 0x00:
                    break
            except asyncio.TimeoutError:
                continue
            except Exception:
                break

    recv_task = asyncio.create_task(receive_ai_playback())

    for idx, turn in enumerate(SIMULATION_SCRIPT, start=1):
        print("\n" + "-" * 75)
        print(f" TURN {idx} / {len(SIMULATION_SCRIPT)}")
        print("-" * 75)
        
        caller_txt = turn["text"]
        lang = turn["lang"]
        try:
            print(f"\n[CUSTOMER (BOT A)]: \"{caller_txt}\"", flush=True)
        except Exception:
            print(f"\n[CUSTOMER (BOT A)]: \"{caller_txt.encode('ascii', 'replace').decode('ascii')}\"")
        
        # 1. Synthesize Customer Voice
        caller_pcm = synthesize_caller_speech(caller_txt, lang=lang)
        
        # Play customer speech through supervisor speaker
        play_speaker(caller_pcm)

        # Stream customer audio frames into Call Gateway (20ms frames)
        frame_size = 320
        for i in range(0, len(caller_pcm), frame_size):
            frame = caller_pcm[i:i + frame_size]
            if len(frame) < frame_size:
                frame = frame + b"\x00" * (frame_size - len(frame))
            writer.write(struct.pack("!BH", 0x10, len(frame)) + frame)
            await writer.drain()
            await asyncio.sleep(0.015)

        # Stream 800ms of silence to trigger VAD endpointing
        silence_frame = b"\x00" * 320
        for _ in range(40):  # 40 * 20ms = 800ms
            writer.write(struct.pack("!BH", 0x10, len(silence_frame)) + silence_frame)
            await writer.drain()
            await asyncio.sleep(0.020)

        # Wait for Receptionist Bot B to reply
        print("\n[RECEPTIONIST (BOT B) IS REASONING & RESPONDING...]")
        incoming_ai_chunks.clear()

        # Monitor received audio
        wait_deadline = time.perf_counter() + 9.0
        last_count = 0
        silence_count = 0
        while time.perf_counter() < wait_deadline:
            await asyncio.sleep(0.4)
            current_len = len(incoming_ai_chunks)
            if current_len > 0 and current_len == last_count:
                silence_count += 1
                if silence_count >= 3:  # 1.2s silence after speech -> turn complete
                    break
            else:
                silence_count = 0
            last_count = current_len

        if incoming_ai_chunks:
            ai_pcm = b"".join(incoming_ai_chunks)
            dur_s = len(ai_pcm) / (8000 * 2)
            print(f"[RECEPTIONIST (BOT B)]: Spoke {dur_s:.2f}s of audio back over telephony.")
            # Play Receptionist speech through supervisor speaker
            play_speaker(ai_pcm)
        else:
            print("[RECEPTIONIST (BOT B)]: (Completed turn)")

        await asyncio.sleep(0.8)

    stop_event.set()
    recv_task.cancel()

    # Graceful disconnect
    try:
        writer.write(struct.pack("!BH", 0x00, 0))
        await writer.drain()
        writer.close()
        await writer.wait_closed()
    except Exception:
        pass

    # Check CRM Database Persistence
    db_tags = get_records("customer_tags")
    db_notes = get_records("call_notes")
    db_cbs = get_records("scheduled_callbacks")

    print("\n" + "=" * 75)
    print("  SIMULATION SUPERVISOR AUDIT REPORT")
    print(f"  • Total Turns Executed: {len(SIMULATION_SCRIPT)}")
    print(f"  • CRM Database Records: Tags={len(db_tags)}, Notes={len(db_notes)}, Callbacks={len(db_cbs)}")
    print("========================================================\n")

if __name__ == "__main__":
    asyncio.run(run_live_bot_to_bot_simulation())
