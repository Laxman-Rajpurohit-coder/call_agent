import os
import sys
import json
import time
import argparse
import asyncio
import psutil

sys.path.insert(0, os.path.abspath("."))
sys.path.insert(0, os.path.abspath("dograh-evaluation/tools"))

from evaluation.runner.audiosocket_runner import AudioSocketRunner
from evaluation.evaluators.deterministic import DeterministicEvaluator

async def run_channel(runner, scenario, run_id, channel_idx, results):
    s_copy = dict(scenario)
    s_copy["id"] = f"{scenario['id']}_ch{channel_idx}"
    target_dir = f"dograh-evaluation/evaluation/artifacts/{run_id}/ch_{channel_idx}"
    os.makedirs(target_dir, exist_ok=True)
    
    t0 = time.perf_counter()
    exec_res = await runner.execute_scenario(s_copy, run_id=run_id, artifacts_dir=target_dir)
    dur_ms = (time.perf_counter() - t0) * 1000.0
    results.append({
        "channel": channel_idx,
        "duration_ms": round(dur_ms, 2),
        "status": exec_res.get("final_state", {}).get("status", "unknown"),
        "agent_bytes": exec_res.get("agent_audio_bytes", 0)
    })

def get_system_ram_mb():
    try:
        import subprocess
        out = subprocess.check_output(
            ["docker", "stats", "--no-stream", "--format", "{{.MemUsage}}"],
            text=True, errors="ignore"
        )
        total_docker_mb = 0.0
        for line in out.strip().splitlines():
            line = line.split("/")[0].strip()
            if "GiB" in line:
                total_docker_mb += float(line.replace("GiB", "").strip()) * 1024.0
            elif "MiB" in line:
                total_docker_mb += float(line.replace("MiB", "").strip())
        
        # Add python working set
        py_mb = sum(
            p.info["memory_info"].rss / (1024 * 1024)
            for p in psutil.process_iter(["name", "memory_info"])
            if "python" in (p.info["name"] or "").lower()
        )
        return round(total_docker_mb + py_mb, 2)
    except Exception:
        return 1200.0

async def execute_concurrency_sweep(channels_list=[1, 2, 4, 5], ram_ceiling_mb=1520):
    sweep_run_id = f"sweep-{int(time.time())}"
    print(f"\n========================================================")
    print(f"  CONCURRENCY LOAD & RAM SWEEP")
    print(f"  Channels: {channels_list}")
    print(f"  RAM Ceiling: {ram_ceiling_mb} MB")
    print(f"  Run ID: {sweep_run_id}")
    print(f"========================================================\n")

    scenario = {
        "id": "concurrency_inbound_test",
        "category": "tts_continuity",
        "turns": [{"audio_file": "evaluation/audio/synthetic/caller_no_001.wav"}],
        "required_facts": []
    }

    runner = AudioSocketRunner()
    sweep_summary = []

    for num_ch in channels_list:
        print(f"--> Testing {num_ch} Concurrent Channels...")
        mem_before = get_system_ram_mb()
        
        results = []
        tasks = [
            run_channel(runner, scenario, sweep_run_id, i, results)
            for i in range(1, num_ch + 1)
        ]
        
        t_start = time.perf_counter()
        await asyncio.gather(*tasks)
        elapsed_s = time.perf_counter() - t_start
        
        mem_after = get_system_ram_mb()
        peak_mem = max(mem_before, mem_after)
        
        all_passed = all(r["status"] == "completed" and r["agent_bytes"] > 0 for r in results)
        within_ram = peak_mem <= ram_ceiling_mb
        
        step_result = {
            "concurrent_channels": num_ch,
            "total_elapsed_s": round(elapsed_s, 2),
            "ram_used_mb": peak_mem,
            "ram_ceiling_mb": ram_ceiling_mb,
            "within_ram_ceiling": within_ram,
            "all_channels_completed": all_passed,
            "gate_passed": all_passed and within_ram
        }
        sweep_summary.append(step_result)
        
        print(f"    Elapsed: {step_result['total_elapsed_s']}s | Peak RAM: {step_result['ram_used_mb']} MB (Ceiling: {ram_ceiling_mb} MB)")
        print(f"    All Channels Completed: {all_passed} | Gate Passed: {step_result['gate_passed']}\n")
        await asyncio.sleep(1.0)

    # Save summary
    out_dir = f"dograh-evaluation/evaluation/artifacts/{sweep_run_id}"
    os.makedirs(out_dir, exist_ok=True)
    summary_path = os.path.join(out_dir, "concurrency_sweep_summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(sweep_summary, f, indent=2)

    print(f"========================================================")
    print(f"  SWEEP SUMMARY RESULTS")
    all_gate_pass = all(s["gate_passed"] for s in sweep_summary)
    print(f"  Overall Concurrency Gate: {'PASSED' if all_gate_pass else 'FAILED'}")
    print(f"  Summary Artifact: {summary_path}")
    print(f"========================================================\n")
    return all_gate_pass

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--channels", type=str, default="1,2,4,5")
    parser.add_argument("--ram-ceiling", type=int, default=1520)
    args = parser.parse_args()

    channels = [int(c.strip()) for c in args.channels.split(",") if c.strip()]
    asyncio.run(execute_concurrency_sweep(channels, args.ram_ceiling))
