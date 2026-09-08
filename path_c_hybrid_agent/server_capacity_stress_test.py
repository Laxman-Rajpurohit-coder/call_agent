"""
Server Request Capacity & Limit Stress Benchmark
Ramps through 4 concurrency levels (10 -> 20 -> 30 -> 50 parallel call streams)
to evaluate maximum request capacity, network throughput, and rate limit resilience.
"""

import os
import sys
import time
import psutil
import uuid
import struct
import asyncio
import numpy as np
from typing import List, Dict, Any

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

HOST = "127.0.0.1"
PORT = 9092

LOAD_LEVELS = [10, 20, 30, 50]


async def run_single_stress_channel(cid: int, results: List[Dict[str, Any]]):
    call_id = f"CapacityCall-{cid:02d}"
    t_start = time.perf_counter()
    
    try:
        reader, writer = await asyncio.open_connection(HOST, PORT)
        
        # 1. AudioSocket Header Handshake
        hdr = struct.pack("!BH", 0x01, 16)
        writer.write(hdr + uuid.uuid4().bytes)
        await writer.drain()

        # 2. Receive Initial Greeting (timeout 1.5s)
        greeting_bytes = 0
        t0 = time.perf_counter()
        while time.perf_counter() - t0 < 1.5:
            try:
                g_hdr = await asyncio.wait_for(reader.readexactly(3), timeout=0.2)
                p_type, p_len = struct.unpack("!BH", g_hdr)
                p_data = await reader.readexactly(p_len)
                if p_type == 0x10:
                    greeting_bytes += len(p_data)
            except Exception:
                break

        # 3. Stream Synthetic PCM Audio Frame
        dummy_pcm = b"\x00" * 3200 # 200ms audio
        for i in range(0, len(dummy_pcm), 320):
            writer.write(struct.pack("!BH", 0x10, 320) + dummy_pcm[i:i+320])
        await writer.drain()

        # 4. Wait brief moment & Hangup
        await asyncio.sleep(0.1)
        writer.write(struct.pack("!BH", 0x00, 0))
        await writer.drain()
        writer.close()

        dur = round((time.perf_counter() - t_start) * 1000, 1)
        results.append({
            "cid": cid,
            "call_id": call_id,
            "handshake_ms": dur,
            "greeting_bytes": greeting_bytes,
            "status": "SUCCESS"
        })

    except Exception as e:
        dur = round((time.perf_counter() - t_start) * 1000, 1)
        results.append({
            "cid": cid,
            "call_id": call_id,
            "handshake_ms": dur,
            "greeting_bytes": 0,
            "status": f"FAILED: {e}"
        })


async def run_capacity_stage(num_channels: int) -> Dict[str, Any]:
    print(f"\n⚡ RAMPING LOAD STAGE: {num_channels} Concurrent Parallel Calls...")
    proc = psutil.Process(os.getpid())
    mem_before_mb = proc.memory_info().rss / (1024 * 1024)

    t0 = time.perf_counter()
    results: List[Dict[str, Any]] = []

    # Fire all channels simultaneously
    tasks = [run_single_stress_channel(i + 1, results) for i in range(num_channels)]
    await asyncio.gather(*tasks)

    elapsed_s = round(time.perf_counter() - t0, 3)
    mem_after_mb = proc.memory_info().rss / (1024 * 1024)
    
    success_count = sum(1 for r in results if r["status"] == "SUCCESS")
    success_pct = round((success_count / num_channels) * 100, 1)
    avg_handshake_ms = round(np.mean([r["handshake_ms"] for r in results]), 1)
    calls_per_sec = round(num_channels / max(elapsed_s, 0.001), 1)

    print(f"  📊 Stage Summary for {num_channels} Channels:")
    print(f"     -> Total Execution Time    : {elapsed_s} s")
    print(f"     -> Connection Success Rate : {success_count}/{num_channels} ({success_pct}%)")
    print(f"     -> Avg Connection Handshake: {avg_handshake_ms} ms")
    print(f"     -> Call Handshake Throughput: {calls_per_sec} calls/sec")
    print(f"     -> Process Memory Usage    : {mem_after_mb:.1f} MB (Delta: +{mem_after_mb - mem_before_mb:.1f} MB)")

    return {
        "num_channels": num_channels,
        "elapsed_s": elapsed_s,
        "success_pct": success_pct,
        "avg_handshake_ms": avg_handshake_ms,
        "calls_per_sec": calls_per_sec,
        "mem_mb": round(mem_after_mb, 1)
    }


async def main():
    print("=" * 90)
    print("  🚀 SUPERFONE SERVER REQUEST CAPACITY & LIMIT STRESS BENCHMARK")
    print("  Testing Parallel Channel Scaling from 10 to 50 Concurrent Connections")
    print("=================================================================================\n")

    stage_reports = []
    for count in LOAD_LEVELS:
        report = await run_capacity_stage(count)
        stage_reports.append(report)
        await asyncio.sleep(1.0) # Brief cooldown between stages

    print("\n" + "=" * 90)
    print("  🏆 SERVER CAPACITY & STRESS LIMIT SUMMARY REPORT")
    print("=================================================================================")
    print(f"  {'Concurrent Calls':<18} | {'Success Rate':<15} | {'Throughput (Calls/s)':<22} | {'Avg Latency (ms)':<18} | {'Memory (MB)':<12}")
    print("  " + "-" * 88)

    for r in stage_reports:
        print(f"  {r['num_channels']:<18} | {r['success_pct']:<15}% | {r['calls_per_sec']:<22} | {r['avg_handshake_ms']:<18} | {r['mem_mb']:<12}")

    print("=================================================================================\n")

if __name__ == "__main__":
    asyncio.run(main())
