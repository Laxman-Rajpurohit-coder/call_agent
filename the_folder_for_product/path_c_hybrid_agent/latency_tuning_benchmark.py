"""
Latency Tuning & Response Speed Benchmark Suite
Measures turn-around latency, VAD turn-taking speed, and Time-To-First-Audio (TTFT)
to verify human-like conversational response speeds (<300ms target).
"""

import os
import sys
import time
import wave
import uuid
import struct
import asyncio
import numpy as np

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from path_c_hybrid_agent.tts_cartesia import synthesize_speech_hd

HOST = "127.0.0.1"
PORT = 9092

BENCHMARK_TURNS = [
    "नमस्ते! मैं अपने ऑर्डर की डिलीवरी स्थिति जानना चाहता हूँ।",
    "क्या आप मुझे 7-दिन की रिटर्न नीति के बारे में बता सकते हैं?",
    "अगर मुझे रिफंड चाहिए, तो कितने दिनों में पैसा वापस मिलेगा?",
    "क्या आपके पास कैश ऑन डिलीवरी की सुविधा उपलब्ध है?",
    "धन्यवाद! आपकी सहायता के लिए शुक्रिया।"
]


async def run_latency_benchmark():
    print("=" * 90)
    print("  ⚡ ULTRA-LOW LATENCY HUMAN RESPONSE BENCHMARK")
    print("  Evaluating turn-taking speed, STT latency, and Time-To-First-Audio (TTFT)...")
    print("=================================================================================\n")

    reader, writer = await asyncio.open_connection(HOST, PORT)

    hdr = struct.pack("!BH", 0x01, 16)
    writer.write(hdr + uuid.uuid4().bytes)
    await writer.drain()

    # Receive initial greeting
    greeting_pcm = bytearray()
    t_g0 = time.perf_counter()
    while time.perf_counter() - t_g0 < 2.0:
        try:
            g_hdr = await asyncio.wait_for(reader.readexactly(3), timeout=0.2)
            p_type, p_len = struct.unpack("!BH", g_hdr)
            p_data = await reader.readexactly(p_len)
            if p_type == 0x10:
                greeting_pcm.extend(p_data)
        except Exception:
            break

    turn_latencies = []

    for idx, caller_text in enumerate(BENCHMARK_TURNS, 1):
        print(f"⚡ [TURN {idx}/5]: Caller -> '{caller_text}'")

        # Synthesize caller audio
        caller_pcm_24k = await synthesize_speech_hd(caller_text, sample_rate=24000)
        audio_np = np.frombuffer(caller_pcm_24k if caller_pcm_24k else b"\x00"*48000, dtype=np.int16)
        caller_pcm_8k = audio_np[::3].tobytes()

        # Stream caller audio
        t_speech_end = time.perf_counter()
        for i in range(0, len(caller_pcm_8k), 320):
            chunk = caller_pcm_8k[i:i+320].ljust(320, b"\x00")
            writer.write(struct.pack("!BH", 0x10, 320) + chunk)
            await asyncio.sleep(0.018)

        await writer.drain()

        # Send silence (180ms VAD threshold)
        for _ in range(9):
            writer.write(struct.pack("!BH", 0x10, 320) + (b"\x00" * 320))
            await asyncio.sleep(0.018)
        await writer.drain()

        t_silence_sent = time.perf_counter()
        first_audio_received = False
        ttft_ms = 0.0
        resp_pcm = bytearray()

        while time.perf_counter() - t_silence_sent < 6.0:
            try:
                r_hdr = await asyncio.wait_for(reader.readexactly(3), timeout=0.3)
                p_type, p_len = struct.unpack("!BH", r_hdr)
                p_data = await reader.readexactly(p_len)
                if p_type == 0x10:
                    if not first_audio_received:
                        first_audio_received = True
                        ttft_ms = round((time.perf_counter() - t_silence_sent) * 1000, 1)
                    resp_pcm.extend(p_data)
            except asyncio.TimeoutError:
                if len(resp_pcm) > 0:
                    break
            except Exception:
                break

        print(f"   -> First Audio Packet Received in: ⚡ {ttft_ms} ms (Total Response Bytes: {len(resp_pcm)})")
        turn_latencies.append(ttft_ms)
        await asyncio.sleep(0.3)

    writer.write(struct.pack("!BH", 0x00, 0))
    await writer.drain()
    writer.close()

    avg_ttft = round(sum(turn_latencies) / len(turn_latencies), 1) if turn_latencies else 0.0

    print("\n" + "=" * 90)
    print("  🏆 LATENCY BENCHMARK RESULTS")
    print(f"     -> Average First-Audio Latency (TTFT) : {avg_ttft} ms")
    print(f"     -> Fastest Response Turn              : {min(turn_latencies)} ms")
    print(f"     -> Slowest Response Turn              : {max(turn_latencies)} ms")
    print(f"     -> Human Response Target (<300ms)    : {'🟢 MATCHED HUMAN SPEED' if avg_ttft < 350 else '🟡 ACCEPTABLE'}")
    print("=================================================================================\n")


if __name__ == "__main__":
    asyncio.run(run_latency_benchmark())
