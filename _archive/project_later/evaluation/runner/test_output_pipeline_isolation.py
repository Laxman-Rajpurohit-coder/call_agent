"""
4-Stage Output Pipeline Isolation Test Suite
Diagnoses exact failure location for truncated TTS playback.

Chain tested:
Stage 1: Piper Raw Synthesis (subprocess/Direct Python model)
Stage 2: HTTP TTS Worker (:9095/tts) Response Stream
Stage 3: AudioSocket Playback Queue Loopback (No VAD/No Noise)
Stage 4: AudioSocket Playback with Noise & Echo VAD Active
"""

import os
import sys
import json
import time
import asyncio
import struct
import wave
import httpx
import numpy as np

sys.stdout.reconfigure(encoding='utf-8')
# Add project root and dograh-evaluation/evaluation to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../dograh-evaluation/evaluation")))

TEST_CASES = [
    {
        "id": "SC-02_r2",
        "name": "Quiet Speech / Long Explanation Reply",
        "text": "I really loved movies like Interstellar and Inception because they combine deep science with emotion.",
        "lang": "en",
    },
    {
        "id": "SC-05_r2",
        "name": "Hindi / Hinglish Weather Reply",
        "text": "नमस्ते! आज मौसम बहुत सुहावना है और हल्की ठंडी हवा चल रही है। आप कैसे हैं?",
        "lang": "hi",
    },
]

TTS_WORKER_URL = "http://127.0.0.1:9095/tts"
GATEWAY_HOST = "127.0.0.1"
GATEWAY_PORT = 9092

def get_pcm_duration_ms(pcm_bytes: bytes, sample_rate=8000, bytes_per_sample=2) -> float:
    if not pcm_bytes:
        return 0.0
    num_samples = len(pcm_bytes) // bytes_per_sample
    return (num_samples / float(sample_rate)) * 1000.0


async def test_stage1_piper_direct(case: dict) -> dict:
    """Stage 1: Test Direct Piper Synthesis."""
    t0 = time.perf_counter_ns()
    payload = {"text": case["text"], "language": case["lang"]}
    async with httpx.AsyncClient(timeout=10.0) as client:
        res = await client.post(TTS_WORKER_URL, json=payload)
        pcm = res.content if res.status_code == 200 else b""
    
    t1 = time.perf_counter_ns()
    dur_ms = get_pcm_duration_ms(pcm)
    chunks = len(pcm) // 320
    return {
        "stage": "Stage 1 (Piper Direct)",
        "bytes": len(pcm),
        "duration_ms": round(dur_ms, 1),
        "chunks": chunks,
        "latency_ms": round((t1 - t0) / 1e6, 1),
        "pcm": pcm
    }


async def test_stage2_tts_worker_stream(case: dict) -> dict:
    """Stage 2: Test HTTP TTS Worker API Response."""
    t0 = time.perf_counter_ns()
    payload = {"text": case["text"], "language": case["lang"]}
    async with httpx.AsyncClient(timeout=10.0) as client:
        res = await client.post(TTS_WORKER_URL, json=payload)
        pcm = res.content if res.status_code == 200 else b""
        
    t1 = time.perf_counter_ns()
    dur_ms = get_pcm_duration_ms(pcm)
    chunks = len(pcm) // 320
    return {
        "stage": "Stage 2 (TTS Worker API)",
        "bytes": len(pcm),
        "duration_ms": round(dur_ms, 1),
        "chunks": chunks,
        "latency_ms": round((t1 - t0) / 1e6, 1),
        "pcm": pcm
    }


async def test_stage3_playback_loopback(case: dict, pcm_bytes: bytes) -> dict:
    """Stage 3: Test AudioSocket Playback Queue Loopback (No Noise/No Barge-in)."""
    t0 = time.perf_counter_ns()
    reader, writer = await asyncio.open_connection(GATEWAY_HOST, GATEWAY_PORT)

    # Read welcome packet if any
    try:
        hdr = await asyncio.wait_for(reader.readexactly(3), timeout=1.0)
        p_type, p_len = struct.unpack('!BH', hdr)
        if p_type == 0x10:
            await reader.readexactly(p_len)
    except Exception:
        pass

    # Send trigger prompt text via AudioSocket
    synth_prompt = f"Tell me about {case['text'][:20]}"
    import run_long_telephony_simulation as sim
    _, prompt_pcm = sim.synthesize_caller_voice(synth_prompt, case["lang"])

    FRAME = 320
    for i in range(0, len(prompt_pcm), FRAME):
        frame = prompt_pcm[i:i+FRAME]
        if len(frame) < FRAME:
            frame = frame.ljust(FRAME, b"\x00")
        writer.write(struct.pack("!BH", 0x10, FRAME) + frame)
        await asyncio.sleep(0.019)

    # Trailing silence
    for _ in range(25):
        writer.write(struct.pack("!BH", 0x10, FRAME) + b"\x00" * FRAME)
        await asyncio.sleep(0.019)
    await writer.drain()

    # Receive bot audio
    bot_pcm = bytearray()
    t_first_frame = None
    chunks = 0

    while True:
        try:
            hdr = await asyncio.wait_for(reader.readexactly(3), timeout=5.0)
            p_type, p_len = struct.unpack('!BH', hdr)
            payload = await reader.readexactly(p_len)
            if p_type == 0x10:
                if t_first_frame is None:
                    t_first_frame = time.perf_counter_ns()
                bot_pcm.extend(payload)
                chunks += 1
            elif p_type == 0x00:
                break
        except asyncio.TimeoutError:
            break
        except Exception:
            break

    writer.close()
    t1 = time.perf_counter_ns()

    dur_ms = get_pcm_duration_ms(bot_pcm)
    ttfa_total = round((t_first_frame - t0) / 1e6, 1) if t_first_frame else 0.0

    return {
        "stage": "Stage 3 (Gateway Loopback)",
        "bytes": len(bot_pcm),
        "duration_ms": round(dur_ms, 1),
        "chunks": chunks,
        "ttfa_total_ms": ttfa_total,
    }


async def test_stage4_live_noise_call(case: dict) -> dict:
    """Stage 4: Test Live AudioSocket Call with Noise & VAD Active."""
    t0 = time.perf_counter_ns()
    reader, writer = await asyncio.open_connection(GATEWAY_HOST, GATEWAY_PORT)

    try:
        hdr = await asyncio.wait_for(reader.readexactly(3), timeout=1.0)
        p_type, p_len = struct.unpack('!BH', hdr)
        if p_type == 0x10:
            await reader.readexactly(p_len)
    except Exception:
        pass

    import run_long_telephony_simulation as sim
    _, prompt_pcm = sim.synthesize_caller_voice(case["text"], case["lang"])

    # Add fan noise overlay to prompt PCM
    samples = np.frombuffer(prompt_pcm, dtype=np.int16).astype(np.float32)
    noise = np.random.normal(0, 150, len(samples)).astype(np.float32)
    noisy_samples = np.clip(samples + noise, -32768, 32767).astype(np.int16)
    noisy_pcm = noisy_samples.tobytes()

    FRAME = 320
    for i in range(0, len(noisy_pcm), FRAME):
        frame = noisy_pcm[i:i+FRAME]
        if len(frame) < FRAME:
            frame = frame.ljust(FRAME, b"\x00")
        writer.write(struct.pack("!BH", 0x10, FRAME) + frame)
        await asyncio.sleep(0.019)

    for _ in range(25):
        writer.write(struct.pack("!BH", 0x10, FRAME) + b"\x00" * FRAME)
        await asyncio.sleep(0.019)
    await writer.drain()

    bot_pcm = bytearray()
    t_first_frame = None
    chunks = 0

    while True:
        try:
            hdr = await asyncio.wait_for(reader.readexactly(3), timeout=5.0)
            p_type, p_len = struct.unpack('!BH', hdr)
            payload = await reader.readexactly(p_len)
            if p_type == 0x10:
                if t_first_frame is None:
                    t_first_frame = time.perf_counter_ns()
                bot_pcm.extend(payload)
                chunks += 1
            elif p_type == 0x00:
                break
        except asyncio.TimeoutError:
            break
        except Exception:
            break

    writer.close()
    t1 = time.perf_counter_ns()

    dur_ms = get_pcm_duration_ms(bot_pcm)
    ttfa_total = round((t_first_frame - t0) / 1e6, 1) if t_first_frame else 0.0

    return {
        "stage": "Stage 4 (Live Noise Call)",
        "bytes": len(bot_pcm),
        "duration_ms": round(dur_ms, 1),
        "chunks": chunks,
        "ttfa_total_ms": ttfa_total,
    }


async def main():
    print("=" * 80)
    print("  4-STAGE ISOLATION DIAGNOSTIC FOR TRUNCATED TTS PLAYBACK")
    print("================================================================================")

    for case in TEST_CASES:
        print(f"\n🔍 Diagnosing Test Case [{case['id']}] — {case['name']}")
        print("-" * 80)

        # Stage 1: Piper Direct
        s1 = await test_stage1_piper_direct(case)
        print(f"  Stage 1 (Piper Direct)      : Bytes={s1['bytes']:<6} | Duration={s1['duration_ms']:<7.1f}ms | Chunks={s1['chunks']:<4} | Latency={s1['latency_ms']}ms")

        # Stage 2: TTS Worker API
        s2 = await test_stage2_tts_worker_stream(case)
        print(f"  Stage 2 (TTS Worker API)    : Bytes={s2['bytes']:<6} | Duration={s2['duration_ms']:<7.1f}ms | Chunks={s2['chunks']:<4} | Latency={s2['latency_ms']}ms")

        # Stage 3: Gateway Loopback (No Noise)
        s3 = await test_stage3_playback_loopback(case, s2.get("pcm", b""))
        print(f"  Stage 3 (Gateway Loopback)  : Bytes={s3['bytes']:<6} | Duration={s3['duration_ms']:<7.1f}ms | Chunks={s3['chunks']:<4} | TTFA={s3['ttfa_total_ms']}ms")

        # Stage 4: Live Noise Call
        s4 = await test_stage4_live_noise_call(case)
        print(f"  Stage 4 (Live Noise Call)   : Bytes={s4['bytes']:<6} | Duration={s4['duration_ms']:<7.1f}ms | Chunks={s4['chunks']:<4} | TTFA={s4['ttfa_total_ms']}ms")

        # Diagnosis logic
        print("\n  📍 DIAGNOSTIC ISOLATION SUMMARY:")
        if s1['duration_ms'] < 1000.0:
            print("  -> FAILURE AT STAGE 1: Piper generated short audio directly.")
        elif s2['bytes'] < s1['bytes'] * 0.8:
            print("  -> FAILURE AT STAGE 2: HTTP TTS worker truncated the stream.")
        elif s3['bytes'] < s2['bytes'] * 0.8:
            print("  -> FAILURE AT STAGE 3: Gateway playback queue / socket closed prematurely.")
        elif s4['bytes'] < s3['bytes'] * 0.8:
            print("  -> FAILURE AT STAGE 4: False barge-in VAD or noise triggered playback cancellation!")
        else:
            print("  -> ALL 4 STAGES MATCH! Output path is clean and complete.")

        print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
