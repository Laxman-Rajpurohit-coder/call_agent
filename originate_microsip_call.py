import asyncio
import os
import sys
import time
import struct
import httpx

ROOT_DIR = r"c:\daily_works\superfone_call"
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from services.dashboard.app.services.script_engine import ScriptEngine

async def run_live_call_session():
    print("=" * 60)
    print("  SUPERFONE AI VOICE PLATFORM - MICROSIP TELEPHONY CONNECTOR")
    print("=" * 60)

    # 1. Connect to AudioSocket Gateway on Port 9092
    try:
        print("[Telephony Bridge] Opening AudioSocket TCP Connection to 127.0.0.1:9092...")
        reader, writer = await asyncio.open_connection('127.0.0.1', 9092)
        print("[Telephony Bridge] Connected to AudioSocket Gateway!")

        # Send UUID header (Type 0x01, Length 16)
        call_uuid = "microsip_call_1"
        uuid_bytes = call_uuid.encode('ascii').ljust(16, b'\x00')[:16]
        header = struct.pack('!BH', 0x01, len(uuid_bytes))
        writer.write(header + uuid_bytes)
        await writer.drain()

        # Send Audio Chunk (Type 0x10) to trigger STT & LLM
        audio_chunk = b'\x00' * 320
        for _ in range(50):
            h = struct.pack('!BH', 0x10, len(audio_chunk))
            writer.write(h + audio_chunk)
            await writer.drain()
            await asyncio.sleep(0.02)

        print("[Telephony Bridge] Spoken turn audio packet sent. Waiting for AI bot audio response...")

        # Read response audio stream
        total_resp = 0
        while total_resp < 16000:
            hdr = await reader.readexactly(3)
            p_type, p_len = struct.unpack('!BH', hdr)
            payload = await reader.readexactly(p_len)
            if p_type == 0x10:
                total_resp += len(payload)

        print(f"[Telephony Bridge] SUCCESS: AI Voice Bot responded with {total_resp} bytes of 8kHz audio!")

        # Hangup
        writer.write(struct.pack('!BH', 0x00, 0))
        await writer.drain()
        writer.close()
        await writer.wait_closed()
        print("[Telephony Bridge] Call session completed cleanly.")

    except Exception as e:
        print(f"[Telephony Bridge Warning] Gateway on 9092 not active: {e}")
        print("[Telephony Bridge] Triggering fallback pipeline test...")
        
        # Fallback to direct pipeline
            tts_res = await client.post("http://127.0.0.1:9095/tts", json={"text": "Namaste."}, timeout=10.0)
            if tts_res.status_code == 200:
                print(f"[Pipeline Success] Generated {len(tts_res.content)} bytes of greeting speech audio!")

if __name__ == "__main__":
    asyncio.run(run_live_call_session())

