"""
load_test.py — Phase 3 parameterised load test.

Usage:
    python load_test.py --calls N [--output FILE]

Runs N concurrent simulated AudioSocket calls against the gateway, collects
per-call and system-level evidence, and writes a JSON result file.

Per-call fields come from two sources:
  - simulate_call()   : accepted/rejected, success/failure, audio_bytes, total_ms
  - Gateway log       : STT/LLM/TTS queue_wait, inference, lock_wait per call_id

System monitoring: 1 Hz psutil background thread refreshing the full Superfone
process tree (gateway + STT/LLM/TTS services + all spawned children) each tick.

Aggregate process RSS is labeled as potentially double-counted due to shared
pages (model memory, shared libs). system_memory_percent is the authoritative
RAM safety metric.
"""

import argparse
import asyncio
import json
import os
import re
import struct
import sys
import threading
import time
from pathlib import Path
from typing import Optional
import statistics

import httpx
import numpy as np
import psutil

# ── Config ────────────────────────────────────────────────────────────────────

GATEWAY_HOST = "127.0.0.1"
GATEWAY_PORT = 9092
TTS_URL = "http://127.0.0.1:9095/tts"
GATEWAY_LOG_PATHS = [
    Path(r"C:\Users\msanj\.gemini\antigravity\brain\037bf89a-6d5c-4059-9740-14ac4588dffa\.system_generated\tasks\task-1286.log"),
]

# Scripts used to identify service processes in the process tree
SERVICE_SCRIPT_FRAGMENTS = [
    "services/stt/worker.py",
    "services/llm/server.py",
    "services/tts/worker.py",
    "services/call_gateway/server.py",
    r"services\stt\worker.py",
    r"services\llm\server.py",
    r"services\tts\worker.py",
    r"services\call_gateway\server.py",
]

# ── Process tree discovery ────────────────────────────────────────────────────

def find_service_pids() -> list[int]:
    """
    Scan running Python processes whose cmdline contains a known Superfone
    service script fragment. Returns all matching PIDs plus their recursive
    children (worker pool processes, Piper subprocesses, etc.).
    """
    pids = set()
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            cmdline = " ".join(proc.info.get("cmdline") or [])
            if any(frag in cmdline for frag in SERVICE_SCRIPT_FRAGMENTS):
                pids.add(proc.pid)
                try:
                    for child in proc.children(recursive=True):
                        pids.add(child.pid)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    return list(pids)


def sample_resources(pids: list[int]) -> dict:
    """
    Sample CPU % and RSS for each PID. Returns aggregate RSS and system stats.
    NOTE: aggregate RSS may double-count shared memory pages (model weights,
    shared libs). system_memory_percent is the authoritative RAM safety metric.
    """
    total_rss_bytes = 0
    total_cpu = 0.0
    proc_count = 0
    for pid in pids:
        try:
            p = psutil.Process(pid)
            mi = p.memory_info()
            total_rss_bytes += mi.rss
            total_cpu += p.cpu_percent(interval=None)
            proc_count += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    mem = psutil.virtual_memory()
    return {
        "process_tree_rss_mb": round(total_rss_bytes / 1024 / 1024, 1),
        "process_tree_cpu_percent": round(total_cpu, 1),
        "process_count": proc_count,
        "system_cpu_percent": psutil.cpu_percent(interval=None),
        "system_memory_percent": round(mem.percent, 1),
        "system_memory_available_mb": round(mem.available / 1024 / 1024, 1),
    }


# ── System monitor thread ─────────────────────────────────────────────────────

class SystemMonitor:
    """
    Background thread sampling the Superfone process tree at 1 Hz.
    Process tree is re-discovered each tick to capture late-spawned children
    (pool workers, Piper subprocesses spawned after test start).
    """

    def __init__(self):
        self.samples: list[dict] = []
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        # Prime cpu_percent() accumulators
        for pid in find_service_pids():
            try:
                psutil.Process(pid).cpu_percent(interval=None)
            except Exception:
                pass
        psutil.cpu_percent(interval=None)
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._thread.join(timeout=3)

    def _run(self):
        while not self._stop.is_set():
            pids = find_service_pids()
            s = sample_resources(pids)
            s["ts"] = time.time()
            self.samples.append(s)
            self._stop.wait(timeout=1.0)

    def summary(self) -> dict:
        if not self.samples:
            return {}
        cpu_sys = [s["system_cpu_percent"] for s in self.samples]
        mem_pct = [s["system_memory_percent"] for s in self.samples]
        rss = [s["process_tree_rss_mb"] for s in self.samples]
        return {
            "cpu_mean_percent": round(statistics.mean(cpu_sys), 1),
            "cpu_max_percent": round(max(cpu_sys), 1),
            "memory_mean_percent": round(statistics.mean(mem_pct), 1),
            "memory_max_percent": round(max(mem_pct), 1),
            "process_tree_rss_mb_mean": round(statistics.mean(rss), 1),
            "process_tree_rss_mb_max": round(max(rss), 1),
            "rss_note": (
                "Aggregate process RSS; may include shared-memory double-counting "
                "(model weights, shared libs). system_memory_percent is the "
                "authoritative RAM safety metric."
            ),
            "samples": len(self.samples),
        }


# ── Audio synthesis ───────────────────────────────────────────────────────────

async def get_speech_audio() -> bytes:
    """
    Load the pre-recorded human speech WAV file from the artifacts directory,
    decode and resample it to 8kHz mono s16 PCM, and return a 3.5-second snippet
    (56000 bytes). This ensures high-confidence STT transcription (avoiding synthetic-voice
    hallucinations) so the pipeline advances past STT into the LLM and TTS stages.
    """
    import av
    path = r"C:\Users\msanj\.gemini\antigravity\brain\037bf89a-6d5c-4059-9740-14ac4588dffa\scratch\welcome.wav"
    container = av.open(path)
    stream = container.streams.audio[0]
    resampler = av.AudioResampler(format='s16', layout='mono', rate=8000)
    
    frames = []
    for frame in container.decode(stream):
        resampled = resampler.resample(frame)
        for r_frame in resampled:
            frames.append(r_frame.to_ndarray())
            
    audio_bytes = b"".join([f.tobytes() for f in frames])
    # 3.5 seconds of audio @ 8000 Hz, 16-bit mono = 3.5 * 8000 * 2 = 56000 bytes
    return audio_bytes[:56000]




# ── Call simulation ───────────────────────────────────────────────────────────

async def simulate_call(call_id: str, speech_audio: bytes) -> dict:
    """
    Simulate one AudioSocket call. Returns per-call result dict.
    Detects admission rejection from the first packet received (hangup = 0x00).
    """
    result = {
        "call_id": call_id,
        "accepted": None,
        "success": False,
        "failure_mode": None,
        "audio_bytes_received": 0,
        "total_call_ms": 0.0,
        # Greeting path (from gateway log)
        "greeting_tts_outcome": None,   # "completed" | "TIMEOUT" | None
        "greeting_tts_gateway_ms": None,
        "greeting_tts_queue_wait_ms": None,
        "greeting_tts_inference_ms": None,
        # Stage latencies (from gateway log)
        "stt_queue_wait_ms": None,
        "stt_preprocess_ms": None,
        "stt_inference_ms": None,
        "worker_pid": None,
        "llm_lock_wait_ms": None,
        "llm_inference_ms": None,
        "tts_queue_wait_ms": None,
        "tts_inference_ms": None,
    }


    t_start = time.perf_counter()
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(GATEWAY_HOST, GATEWAY_PORT), timeout=5.0
        )
    except Exception as e:
        result["failure_mode"] = f"connection_error: {e}"
        result["total_call_ms"] = (time.perf_counter() - t_start) * 1000.0
        return result

    response_received_event = asyncio.Event()
    response_bytes = 0

    async def read_response():
        nonlocal response_bytes
        try:
            while True:
                hdr = await reader.readexactly(3)
                p_type, p_len = struct.unpack('!BH', hdr)
                payload = await reader.readexactly(p_len)
                if p_type == 0x10:
                    response_bytes += len(payload)
                    if response_bytes >= 15000:
                        response_received_event.set()
                        break
                elif p_type == 0x00:
                    response_received_event.set()
                    break
        except Exception:
            pass
        finally:
            response_received_event.set()

    reader_task = None
    try:
        # Send UUID header
        uuid_bytes = call_id.encode('ascii').ljust(16, b'\x00')[:16]
        writer.write(struct.pack('!BH', 0x01, len(uuid_bytes)) + uuid_bytes)
        await writer.drain()

        # Read first packet — hangup (0x00) means admission rejected
        try:
            hdr = await asyncio.wait_for(reader.readexactly(3), timeout=8.0)
        except asyncio.TimeoutError:
            # TCP connection succeeded (otherwise open_connection would have failed).
            # Gateway admitted the call (_try_admit passed, since rejected calls
            # receive an immediate hangup packet we would have read above).
            # But no packet arrived within 8s — the greeting TTS request is
            # waiting in the executor queue and hasn't returned yet.
            # This is 'tcp_connected_greeting_timeout': the bottleneck is
            # between gateway admission and the first byte of the greeting audio.
            result["accepted"] = True   # admission happened; no hangup was received
            result["failure_mode"] = "tcp_connected_greeting_timeout"
            result["total_call_ms"] = round((time.perf_counter() - t_start) * 1000.0, 1)
            return result

        p_type, p_len = struct.unpack('!BH', hdr)
        if p_type == 0x00:
            result["accepted"] = False
            result["failure_mode"] = "admission_rejected"
            result["total_call_ms"] = (time.perf_counter() - t_start) * 1000.0
            return result

        result["accepted"] = True
        # Consume the rest of this first packet
        await reader.readexactly(p_len)

        # Drain welcome greeting.
        # Timeout must exceed the maximum observed greeting TTS latency.
        # At N=15, greeting queue_wait reached 4047ms, total gateway_ms=4576ms.
        # Use 7s to ensure the full greeting is drained before sending speech.
        # A 0.8s silence after the last greeting chunk indicates streaming is done.
        while True:
            try:
                hdr = await asyncio.wait_for(reader.readexactly(3), timeout=7.0)
                p_type, p_len = struct.unpack('!BH', hdr)
                await reader.readexactly(p_len)
            except asyncio.TimeoutError:
                break

        # Post-greeting silence gap: send 4s of silence before speech to
        # ensure the gateway's VAD silence timer (1.0s) has fired and the
        # audio buffer is empty. Without sufficient silence, greeting audio
        # that is still being streamed overlaps with the caller's speech
        # frames and contaminates the STT input.
        silence = b'\x00' * 320
        for _ in range(200):   # 4.0 s @ 20 ms/frame
            writer.write(struct.pack('!BH', 0x10, 320) + silence)
            await writer.drain()
            await asyncio.sleep(0.02)

        reader_task = asyncio.create_task(read_response())

        # Send speech audio frames (20 ms chunks)
        chunk_size = 320
        for i in range(0, len(speech_audio), chunk_size):
            chunk = speech_audio[i:i+chunk_size]
            writer.write(struct.pack('!BH', 0x10, len(chunk)) + chunk)
            await writer.drain()
            await asyncio.sleep(0.02)

        # Stream silence to drive VAD silence timer, wait for AI response.
        # 1500 × 20ms = 30s max — covers LLM serialization at high concurrency.
        for _ in range(1500):
            if response_received_event.is_set():
                break
            writer.write(struct.pack('!BH', 0x10, 320) + silence)
            await writer.drain()
            await asyncio.sleep(0.02)

        if not response_received_event.is_set():
            result["failure_mode"] = "response_timeout"
        elif response_bytes < 15000:
            result["failure_mode"] = f"insufficient_audio: {response_bytes}B"
        else:
            result["success"] = True

        result["audio_bytes_received"] = response_bytes

        # Hangup
        writer.write(struct.pack('!BH', 0x00, 0))
        await writer.drain()

    except asyncio.TimeoutError:
        result["failure_mode"] = "timeout_waiting_for_greeting"
    except Exception as e:
        result["failure_mode"] = f"error: {e}"
    finally:
        if reader_task:
            reader_task.cancel()
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass

    result["total_call_ms"] = round((time.perf_counter() - t_start) * 1000.0, 1)
    return result


# ── Log parsing ───────────────────────────────────────────────────────────────

def call_id_hex(call_id_str: str) -> str:
    """Convert ASCII call_id to the hex form used in gateway logs."""
    return call_id_str.encode('ascii').ljust(16, b'\x00')[:16].hex()


def parse_gateway_log(log_path: Path, call_ids: list[str], after_ts: float) -> dict[str, dict]:
    """
    Parse the gateway log for STT/LLM/TTS per-stage telemetry for each call_id.
    Only lines timestamped at or after after_ts (epoch) are considered.
    Returns dict keyed by call_id_str -> stage metrics.
    """
    hex_to_str = {call_id_hex(cid): cid for cid in call_ids}
    metrics: dict[str, dict] = {cid: {} for cid in call_ids}

    stt_end_re = re.compile(
        r"\bSTT_END call_id=(\S+).*?"
        r"queue_wait_ms=([\d.]+).*?preprocess_ms=([\d.]+).*?inference_ms=([\d.]+).*?worker_pid=(\d+)"
    )
    llm_end_re = re.compile(
        r"\bLLM_END call_id=(\S+).*?"
        r"lock_wait_ms=([\d.]+).*?inference_ms=([\d.]+)"
    )
    tts_end_re = re.compile(
        r"\bTTS_END call_id=(\S+).*?"
        r"queue_wait_ms=([\d.]+).*?inference_ms=([\d.]+)"
    )
    greeting_start_re = re.compile(r"\bGREETING_TTS_START call_id=(\S+)")
    greeting_end_re = re.compile(
        r"\bGREETING_TTS_END call_id=(\S+).*?gateway_ms=([\d.]+)"
        r".*?queue_wait_ms=([\S]+).*?inference_ms=([\S]+)"
    )
    greeting_timeout_re = re.compile(
        r"\bGREETING_TTS_TIMEOUT call_id=(\S+).*?elapsed_ms=([\d.]+)"
    )

    # Timestamp format: 2026-08-19 11:00:49,123
    ts_re = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),(\d+)")

    if not log_path.exists():
        return metrics

    with open(log_path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            # Check timestamp
            tm = ts_re.match(line)
            if tm:
                try:
                    import datetime
                    dt = datetime.datetime.strptime(tm.group(1), "%Y-%m-%d %H:%M:%S")
                    line_epoch = dt.timestamp()
                    if line_epoch < after_ts - 2:   # 2s grace
                        continue
                except Exception:
                    pass

            m = stt_end_re.search(line)
            if m:
                cid_hex = m.group(1)
                cid = hex_to_str.get(cid_hex)
                if cid:
                    metrics[cid].update({
                        "stt_queue_wait_ms": float(m.group(2)),
                        "stt_preprocess_ms": float(m.group(3)),
                        "stt_inference_ms": float(m.group(4)),
                        "worker_pid": int(m.group(5)),
                    })
                continue


            m = llm_end_re.search(line)
            if m:
                cid_hex = m.group(1)
                cid = hex_to_str.get(cid_hex)
                if cid:
                    metrics[cid].update({
                        "llm_lock_wait_ms": float(m.group(2)),
                        "llm_inference_ms": float(m.group(3)),
                    })
                continue

            m = tts_end_re.search(line)
            if m:
                cid_hex = m.group(1)
                cid = hex_to_str.get(cid_hex)
                if cid:
                    metrics[cid].update({
                        "tts_queue_wait_ms": float(m.group(2)),
                        "tts_inference_ms": float(m.group(3)),
                    })
                continue

            m = greeting_end_re.search(line)
            if m:
                cid_hex = m.group(1)
                cid = hex_to_str.get(cid_hex)
                if cid:
                    metrics[cid].update({
                        "greeting_tts_gateway_ms": float(m.group(2)),
                        "greeting_tts_queue_wait_ms": str(m.group(3)),
                        "greeting_tts_inference_ms": str(m.group(4)),
                        "greeting_tts_outcome": "completed",
                    })
                continue

            m = greeting_timeout_re.search(line)
            if m:
                cid_hex = m.group(1)
                cid = hex_to_str.get(cid_hex)
                if cid:
                    metrics[cid].update({
                        "greeting_tts_gateway_ms": float(m.group(2)),
                        "greeting_tts_outcome": "TIMEOUT",
                    })

    return metrics


def find_current_gateway_log() -> Optional[Path]:
    """Find the most recently modified gateway log file."""
    candidates = list(GATEWAY_LOG_PATHS)
    # Also scan task log directory for any server.py task log
    task_dir = Path(r"C:\Users\msanj\.gemini\antigravity\brain\037bf89a-6d5c-4059-9740-14ac4588dffa\.system_generated\tasks")
    if task_dir.exists():
        for p in sorted(task_dir.glob("task-*.log"), key=lambda x: x.stat().st_mtime, reverse=True):
            try:
                content = p.read_text(encoding="utf-8", errors="replace")
                if "AudioSocket Gateway Server" in content or "ADMISSION_ACCEPTED" in content:
                    candidates.insert(0, p)
                    break
            except Exception:
                pass
    for p in candidates:
        if p.exists():
            return p
    return None


# ── Statistics helpers ────────────────────────────────────────────────────────

def pct(values: list[float], p: int) -> float:
    if not values:
        return 0.0
    sorted_v = sorted(values)
    idx = int(len(sorted_v) * p / 100)
    return round(sorted_v[min(idx, len(sorted_v) - 1)], 2)


def compute_summary(call_results: list[dict]) -> dict:
    accepted = [r for r in call_results if r.get("accepted")]
    rejected = [r for r in call_results if r.get("accepted") is False]
    succeeded = [r for r in accepted if r.get("success")]
    # greeting_timeout: admitted but TTS pool was exhausted before client got greeting
    greeting_timeout = [r for r in accepted if r.get("failure_mode") == "tcp_connected_greeting_timeout"]
    # pipeline_failed: admitted, greeting received, but failed during STT/LLM/TTS
    pipeline_failed = [r for r in accepted
                       if not r.get("success") and r.get("failure_mode") != "tcp_connected_greeting_timeout"]

    def field(lst, key):
        return [r[key] for r in lst if r.get(key) is not None]

    stt_qw = field(succeeded, "stt_queue_wait_ms")
    llm_lw = field(succeeded, "llm_lock_wait_ms")
    tts_qw = field(succeeded, "tts_queue_wait_ms")

    any_llm_timeout = any(
        "timeout" in str(r.get("failure_mode", "")).lower() and
        "response" in str(r.get("failure_mode", "")).lower()
        for r in pipeline_failed
    )
    llm_lw_p95 = pct(llm_lw, 95)
    early_warning = llm_lw_p95 > 5000
    # Saturation: any LLM timeout OR lock-wait p95 > 7000 on two consecutive levels
    # (consecutive check is done in the ladder loop, not per-level)
    saturation = any_llm_timeout or llm_lw_p95 > 7000

    return {
        "total_calls": len(call_results),
        "accepted": len(accepted),
        "rejected": len(rejected),
        "succeeded": len(succeeded),
        "greeting_timeout": len(greeting_timeout),   # admitted, TTS pool exhausted before greeting
        "pipeline_failed": len(pipeline_failed),     # admitted+greeted, failed during STT/LLM/TTS
        "failure_modes": [r["failure_mode"] for r in pipeline_failed if r.get("failure_mode")],

        "stt_queue_wait_p50_ms": pct(stt_qw, 50),
        "stt_queue_wait_p95_ms": pct(stt_qw, 95),
        "stt_queue_wait_max_ms": round(max(stt_qw), 2) if stt_qw else 0.0,
        "stt_inference_p95_ms": pct(field(succeeded, "stt_inference_ms"), 95),

        "llm_lock_wait_p50_ms": pct(llm_lw, 50),
        "llm_lock_wait_p95_ms": llm_lw_p95,
        "llm_lock_wait_max_ms": round(max(llm_lw), 2) if llm_lw else 0.0,
        "llm_inference_p95_ms": pct(field(succeeded, "llm_inference_ms"), 95),

        "tts_queue_wait_p50_ms": pct(tts_qw, 50),
        "tts_queue_wait_p95_ms": pct(tts_qw, 95),
        "tts_queue_wait_max_ms": round(max(tts_qw), 2) if tts_qw else 0.0,
        "tts_inference_p95_ms": pct(field(succeeded, "tts_inference_ms"), 95),

        "any_llm_timeout": any_llm_timeout,
        "early_warning_triggered": early_warning,   # llm_lock_wait p95 > 5000ms
        "saturation_triggered": saturation,         # timeout OR p95 > 7000ms
    }


# ── Main test runner ──────────────────────────────────────────────────────────

async def run_test(n_calls: int, output_path: Path) -> dict:
    print(f"\n{'='*60}")
    print(f"Load test: N={n_calls} concurrent calls")
    print(f"Output: {output_path}")
    print(f"{'='*60}")

    # Test isolation check
    print("Checking system state before test...")
    pre_pids = find_service_pids()
    print(f"  Service processes found: {len(pre_pids)} PIDs: {pre_pids}")

    # Generate speech audio
    print("Generating speech audio via TTS warmup call...")
    speech_audio = await get_speech_audio()
    print(f"  Speech audio: {len(speech_audio)} bytes")

    # Warm up STT service worker pool (4 workers)
    print("Warming up STT service worker pool concurrently...")
    dummy_pcm = b"\x00" * 1600  # 100ms of silence @ 8kHz PCM16 mono

    async def single_warmup(idx: int, client: httpx.AsyncClient) -> int:
        try:
            resp = await client.post(
                "http://127.0.0.1:9094/stt",
                content=dummy_pcm,
                headers={"X-Enqueue-Time": str(time.time())},
                timeout=15.0
            )
            if resp.status_code == 200:
                data = resp.json()
                pid = data.get("worker_pid", 0)
                return pid
        except Exception as e:
            print(f"  STT warmup request {idx} failed: {e}")
        return 0

    async with httpx.AsyncClient() as client:
        # Submit all 4 requests concurrently to force ProcessPoolExecutor
        # to assign them to 4 distinct worker processes.
        tasks = [single_warmup(i, client) for i in range(4)]
        warmed_pids = await asyncio.gather(*tasks)

    distinct_pids = set(pid for pid in warmed_pids if pid > 0)
    print(f"  STT warmup responses from PIDs: {warmed_pids} (distinct: {len(distinct_pids)})")
    if len(distinct_pids) < 4:
        print(f"  WARNING: Only {len(distinct_pids)} distinct STT workers warmed. System may experience cold-start timeouts.")
    else:
        print("  STT worker pool fully warmed (4 distinct workers verified).")



    # Find gateway log
    log_path = find_current_gateway_log()
    print(f"  Gateway log: {log_path}")
    test_start_epoch = time.time()
    test_start_ts = time.perf_counter()

    # Start resource monitor
    monitor = SystemMonitor()
    monitor.start()

    # Generate call IDs
    call_ids = [f"load{n_calls}_{i:03d}" for i in range(n_calls)]

    # Launch all calls concurrently
    print(f"Launching {n_calls} concurrent calls...")
    tasks = [simulate_call(cid, speech_audio) for cid in call_ids]
    results = await asyncio.gather(*tasks)

    total_elapsed_ms = (time.perf_counter() - test_start_ts) * 1000.0
    monitor.stop()

    print(f"All calls finished in {total_elapsed_ms/1000:.2f}s")

    # Parse gateway log for per-stage metrics
    if log_path:
        print("Parsing gateway log for per-stage telemetry...")
        stage_metrics = parse_gateway_log(log_path, call_ids, test_start_epoch)
        # Merge into results
        results = list(results)
        for r in results:
            m = stage_metrics.get(r["call_id"], {})
            r.update(m)

    summary = compute_summary(results)
    sys_summary = monitor.summary()

    output = {
        "concurrency": n_calls,
        "total_elapsed_ms": round(total_elapsed_ms, 1),
        "test_start_epoch": test_start_epoch,
        "calls": results,
        "system": sys_summary,
        "summary": summary,
    }

    output_path.write_text(json.dumps(output, indent=2))
    print(f"Results written to {output_path}")

    # Print summary
    s = summary
    print(f"\n--- Summary (N={n_calls}) ---")
    print(f"  accepted={s['accepted']} rejected={s['rejected']} succeeded={s['succeeded']} "
          f"greeting_timeout={s['greeting_timeout']} pipeline_failed={s['pipeline_failed']}")
    if s['failure_modes']:
        print(f"  pipeline_failure_modes={s['failure_modes']}")
    print(f"  STT  queue_wait p95={s['stt_queue_wait_p95_ms']}ms  inference p95={s['stt_inference_p95_ms']}ms")
    print(f"  LLM  lock_wait  p50={s['llm_lock_wait_p50_ms']}ms  p95={s['llm_lock_wait_p95_ms']}ms  max={s['llm_lock_wait_max_ms']}ms")
    print(f"  TTS  queue_wait p95={s['tts_queue_wait_p95_ms']}ms  inference p95={s['tts_inference_p95_ms']}ms")
    if sys_summary:
        print(f"  CPU  mean={sys_summary['cpu_mean_percent']}%  max={sys_summary['cpu_max_percent']}%")
        print(f"  RAM  system={sys_summary['memory_mean_percent']}%  tree_rss_mean={sys_summary['process_tree_rss_mb_mean']}MB")
    print(f"  early_warning={s['early_warning_triggered']}  saturation={s['saturation_triggered']}")

    return output


def main():
    parser = argparse.ArgumentParser(description="Phase 3 load test")
    parser.add_argument("--calls", type=int, required=True, help="Number of concurrent calls")
    parser.add_argument("--output", type=str, default=None, help="Output JSON file path")
    args = parser.parse_args()

    n = args.calls
    out_path = Path(args.output) if args.output else Path(f"load_test_results_N{n}.json")

    result = asyncio.run(run_test(n, out_path))
    s = result["summary"]

    # Exit non-zero if saturation triggered (for scripted ladder use)
    if s["saturation_triggered"]:
        print("\nSATURATION TRIGGERED — do not advance ladder.")
        sys.exit(2)
    total_failed = s.get("greeting_timeout", 0) + s.get("pipeline_failed", 0)
    if total_failed > 0 and s.get("accepted", 0) > 0:
        failed_pct = total_failed / max(s.get("accepted", 1), 1) * 100
        if failed_pct > 20:
            print(f"\nFAIL RATE {failed_pct:.0f}% exceeds 20% policy threshold — do not advance ladder.")
            sys.exit(2)



if __name__ == "__main__":
    main()
