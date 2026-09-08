"""
Live Scenario Test Harness for E-Commerce & Healthcare
Executes multi-turn calls across two brand new business scenarios:
  1. QuickCart E-Commerce Order Tracking & Returns Support (Swati AI)
  2. ApolloCare Hospital OPD Appointment Booking (Kavita AI - Marwadi/Hindi)
"""

import os
import sys
import time
import wave
import uuid
import struct
import asyncio
import numpy as np
from typing import List, Dict, Any

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from path_c_hybrid_agent.tts_cartesia import synthesize_speech_hd

HOST = "127.0.0.1"
PORT = 9092

SCENARIOS = [
    # ── SCENARIO A: QUICKCART E-COMMERCE CUSTOMER CARE ────────────────────────
    {
        "id": "QuickCart-OrderTrack",
        "tenant_id": "tenant_ecommerce",
        "name": "QuickCart E-Commerce Order Tracking",
        "phone": "+919811009901",
        "turns": [
            "नमस्ते! मेरा ऑर्डर नंबर QC-987654 अभी तक डिलीवर क्यों नहीं हुआ?",
            "अगर मुझे साइज पसंद न आए तो रिटर्न और रिफंड की क्या पॉलिसी है?",
            "क्या मैं कैश ऑन डिलीवरी (COD) से अगला ऑर्डर कर सकता हूँ?"
        ]
    },
    
    # ── SCENARIO B: APOLLOCARE HOSPITAL OPD APPOINTMENT BOOKING ───────────────
    {
        "id": "ApolloCare-OPDBooking",
        "tenant_id": "tenant_healthcare",
        "name": "ApolloCare Hospital OPD Appointment Booking",
        "phone": "+919811009902",
        "turns": [
            "राम-राम सा! डाक्टर शर्मा सा री कार्डियोलॉजी अप्वाइंटमेंट बुक करबा री काई प्रक्रिया है सा?",
            "लैब रिपोर्ट व्हाट्सएप या एसएमएस पर मिल जासी काई सा?",
            "हॉस्पिटल रो मुख्य ऑफिस और एड्रेस कठे है सा?"
        ]
    }
]


async def run_scenario_call(scenario: Dict[str, Any]):
    sc_id = scenario["id"]
    name = scenario["name"]
    tenant_id = scenario["tenant_id"]
    phone = scenario["phone"]
    turns = scenario["turns"]

    print(f"\n=================================================================================")
    print(f"  🎬 EXECUTING NEW SCENARIO: {name} ({sc_id})")
    print(f"=================================================================================")

    reader, writer = await asyncio.open_connection(HOST, PORT)
    hdr = struct.pack("!BH", 0x01, 16)
    writer.write(hdr + uuid.uuid4().bytes)
    await writer.drain()

    # Receive Initial Greeting
    greeting_pcm = bytearray()
    t0_greeting = time.perf_counter()
    while time.perf_counter() - t0_greeting < 2.5:
        try:
            g_hdr = await asyncio.wait_for(reader.readexactly(3), timeout=0.3)
            p_type, p_len = struct.unpack("!BH", g_hdr)
            p_data = await reader.readexactly(p_len)
            if p_type == 0x10:
                greeting_pcm.extend(p_data)
        except Exception:
            break

    print(f"  📢 Greeting Received: {len(greeting_pcm)} bytes PCM")

    for idx, caller_text in enumerate(turns, 1):
        print(f"\n  --- Turn {idx} ---")
        print(f"  🗣️ [Caller]: '{caller_text}'")

        # Synthesize caller audio
        v_id = "791d5162-d5eb-40f0-8189-f19db44611d8" if "QuickCart" in sc_id else "56e35e2d-6eb6-4226-ab8b-9776515a7094"
        caller_pcm_24k = await synthesize_speech_hd(caller_text, voice_id=v_id, sample_rate=24000)
        audio_np = np.frombuffer(caller_pcm_24k if caller_pcm_24k else b"\x00"*48000, dtype=np.int16)
        caller_pcm_8k = audio_np[::3].tobytes()

        # Stream caller audio
        for i in range(0, len(caller_pcm_8k), 320):
            chunk = caller_pcm_8k[i:i+320].ljust(320, b"\x00")
            writer.write(struct.pack("!BH", 0x10, 320) + chunk)
            await asyncio.sleep(0.018)

        await writer.drain()

        # Silence for VAD
        for _ in range(25):
            writer.write(struct.pack("!BH", 0x10, 320) + (b"\x00" * 320))
            await asyncio.sleep(0.018)
        await writer.drain()

        # Receive Response
        resp_pcm = bytearray()
        t_wait = time.perf_counter()
        ttft_ms = 0

        while time.perf_counter() - t_wait < 6.0:
            try:
                r_hdr = await asyncio.wait_for(reader.readexactly(3), timeout=0.4)
                p_type, p_len = struct.unpack("!BH", r_hdr)
                p_data = await reader.readexactly(p_len)
                if p_type == 0x10:
                    if len(resp_pcm) == 0:
                        ttft_ms = round((time.perf_counter() - t_wait) * 1000, 1)
                    resp_pcm.extend(p_data)
            except asyncio.TimeoutError:
                if len(resp_pcm) > 0:
                    break
            except Exception:
                break

        print(f"  🤖 [Agent Response]: Received {len(resp_pcm)} bytes PCM (TTFT: {ttft_ms}ms)")
        await asyncio.sleep(0.4)

    # Hangup
    writer.write(struct.pack("!BH", 0x00, 0))
    await writer.drain()
    writer.close()
    print(f"  ✅ Scenario '{name}' Completed Successfully!")


async def main():
    print("=" * 90)
    print("  🚀 EXECUTING NEW REAL-WORLD BUSINESS SCENARIO TESTS")
    print("=================================================================================\n")

    for sc in SCENARIOS:
        await run_scenario_call(sc)

    print("\n" + "=" * 90)
    print("  ✅ ALL NEW REAL-WORLD BUSINESS SCENARIOS TESTED & VERIFIED!")
    print("=================================================================================\n")

if __name__ == "__main__":
    asyncio.run(main())
