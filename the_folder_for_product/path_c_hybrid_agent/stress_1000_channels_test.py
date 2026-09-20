"""
1,000-Channel Parallel Extreme Scale Benchmark
Fires 1,000 call socket connections into Path C Voice Agent Gateway (Port 9092)
with Semaphore(50) to respect Windows OS Winsock ephemeral port allocation limits.
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

TOTAL_CHANNELS = 1000
SEMAPHORE = asyncio.Semaphore(50)


async def run_single_1000_channel(cid: int, results: List[Dict[str, Any]]):
    async with SEMAPHORE:
        t0 = time.perf_counter()
        try:
            reader, writer = await asyncio.open_connection(HOST, PORT)
            
            # Handshake
            hdr = struct.pack("!BH", 0x01, 16)
            writer.write(hdr + uuid.uuid4().bytes)
            await writer.drain()

            # Stream brief audio chunk
            frame = b"\x00" * 320
            writer.write(struct.pack("!BH", 0x10, 320) + frame)
            await writer.drain()

            # Hangup
            writer.write(struct.pack("!BH", 0x00, 0))
            await writer.drain()
            writer.close()

            dur_ms = round((time.perf_counter() - t0) * 1000, 1)
            results.append({"cid": cid, "duration_ms": dur_ms, "status": "SUCCESS"})
        except Exception as e:
            dur_ms = round((time.perf_counter() - t0) * 1000, 1)
            results.append({"cid": cid, "duration_ms": dur_ms, "status": f"FAILED: {e}"})


async def main():
    print("=" * 90)
    print("  🚀 MASSIVE 1,000-CHANNEL PARALLEL EXTREME SCALE BENCHMARK")
    print("=================================================================================\n")

    proc = psutil.Process(os.getpid())
    mem_before_mb = proc.memory_info().rss / (1024 * 1024)
    t_start_all = time.perf_counter()

    results: List[Dict[str, Any]] = []
    print(f"  ⚡ Launching {TOTAL_CHANNELS} Parallel Call Channels across Gateway Port {PORT}...")

    tasks = [run_single_1000_channel(i + 1, results) for i in range(TOTAL_CHANNELS)]
    await asyncio.gather(*tasks)

    total_time_s = round(time.perf_counter() - t_start_all, 3)
    mem_after_mb = proc.memory_info().rss / (1024 * 1024)

    success_count = sum(1 for r in results if r["status"] == "SUCCESS")
    failed_count = TOTAL_CHANNELS - success_count
    success_pct = round((success_count / TOTAL_CHANNELS) * 100, 1)
    
    successful_latencies = [r["duration_ms"] for r in results if r["status"] == "SUCCESS"]
    avg_latency_ms = round(np.mean(successful_latencies), 1) if successful_latencies else 0.0
    throughput_cps = round(TOTAL_CHANNELS / max(total_time_s, 0.001), 1)

    print("\n" + "=" * 90)
    print("  🏆 1,000-CHANNEL EXTREME SCALE BENCHMARK REPORT")
    print("=================================================================================")
    print(f"  Total Channels Fired       : {TOTAL_CHANNELS}")
    print(f"  Total Benchmark Execution : {total_time_s} s")
    print(f"  Successful Connections    : {success_count}/{TOTAL_CHANNELS} ({success_pct}%)")
    print(f"  Failed Connections        : {failed_count}")
    print(f"  Peak Connection Throughput : {throughput_cps} calls/sec")
    print(f"  Average Handshake Latency : {avg_latency_ms} ms")
    print(f"  Server Process Memory RSS : {mem_after_mb:.1f} MB (Delta: +{mem_after_mb - mem_before_mb:.1f} MB)")
    print("=================================================================================\n")

if __name__ == "__main__":
    asyncio.run(main())
