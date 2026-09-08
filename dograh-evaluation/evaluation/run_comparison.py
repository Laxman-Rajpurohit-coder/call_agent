import os
import sys
import json
import time
import asyncio
import httpx
from typing import Dict, Any, List

sys.path.insert(0, os.path.abspath("."))
sys.path.insert(0, os.path.abspath("dograh-evaluation/tools"))
from evaluation.runner.audiosocket_runner import AudioSocketRunner
from evaluation.evaluators.deterministic import DeterministicEvaluator
from crm_bridge import exec_tag_customer, exec_save_call_note, exec_schedule_callback, get_records

# ── 25 Comparative Scenarios Matrix ──────────────────────────────────────────

COMPARATIVE_SCENARIOS = [
    # 1. 10 Normal Calls
    *[{"id": f"comp_normal_{i:02d}", "type": "normal", "audio": "evaluation/audio/synthetic/caller_no_001.wav", "text": "What are your hours?"} for i in range(1, 11)],
    # 2. 5 Genuine Interruption Calls
    *[{"id": f"comp_interrupt_{i:02d}", "type": "interruption", "audio": "evaluation/audio/synthetic/caller_actually_address_001.wav", "text": "Actually, tell me the address."} for i in range(1, 6)],
    # 3. 5 Ambient Noise Calls
    *[{"id": f"comp_noise_{i:02d}", "type": "noise", "audio": "evaluation/audio/synthetic/line_hiss_001.wav", "text": "ambient_noise"} for i in range(1, 6)],
    # 4. 5 Long Multi-Sentence Response Calls
    *[{"id": f"comp_long_cadence_{i:02d}", "type": "long_response", "audio": "evaluation/audio/synthetic/quiet_hello_001.wav", "text": "Tell me everything about the foundation."} for i in range(1, 6)],
]

async def run_platform_benchmark(target: str = "current_baseline"):
    run_id = f"comp-run-{int(time.time())}"
    print(f"\n========================================================")
    print(f"  25-CALL COMPARATIVE PLATFORM EVALUATION")
    print(f"  Target Platform: {target}")
    print(f"  Run ID: {run_id}")
    print(f"========================================================\n")

    runner = AudioSocketRunner()
    evaluator = DeterministicEvaluator()

    total = len(COMPARATIVE_SCENARIOS)
    passed = 0
    results = []

    for idx, sc in enumerate(COMPARATIVE_SCENARIOS, start=1):
        s_id = sc["id"]
        s_type = sc["type"]
        print(f"[{idx}/{total}] [{s_type.upper()}] Evaluating {s_id} ...")

        # Map to evaluation scenario format
        scenario_data = {
            "id": s_id,
            "category": "noise_rejection" if s_type == "noise" else ("genuine_barge_in" if s_type == "interruption" else "tts_continuity"),
            "turns": [{"audio_file": sc["audio"]}],
            "required_facts": []
        }

        exec_res = await runner.execute_scenario(scenario_data, run_id=run_id, artifacts_dir="dograh-evaluation/artifacts")
        eval_res = evaluator.evaluate(scenario_data, exec_res)

        if eval_res["passed"]:
            passed += 1
            print(f"  -> [PASS] {eval_res.get('agent_response', '')[:60]}...")
        else:
            print(f"  -> [FAIL] {eval_res.get('failure_reasons')}")

        results.append(eval_res)

    print(f"\n========================================================")
    print(f"  BENCHMARK SUMMARY ({target.upper()})")
    print(f"  Passed: {passed}/{total} ({round(passed/total*100, 1)}%)")
    print(f"========================================================\n")

    # Run CRM Tool Persistence Verification
    print("Verifying CRM Tool Database Actions...")
    t1 = exec_tag_customer("cust_bench_01", "high_priority", "Urgent request in comparative test")
    t2 = exec_save_call_note("call_bench_01", "Automated comparative benchmark call completed", "Follow up with customer", "cust_bench_01")
    t3 = exec_schedule_callback("cust_bench_01", "+919876543210", "2026-08-24T15:00:00Z")

    db_tags = get_records("customer_tags")
    db_notes = get_records("call_notes")
    db_cbs = get_records("scheduled_callbacks")

    tool_success = len(db_tags) > 0 and len(db_notes) > 0 and len(db_cbs) > 0
    print(f"  CRM Database Persistence: {'100% SUCCESS' if tool_success else 'FAILED'}")

    return {
        "target": target,
        "run_id": run_id,
        "total": total,
        "passed": passed,
        "tool_success": tool_success,
        "pass_rate": round(passed / total, 3)
    }

if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "current_baseline"
    asyncio.run(run_platform_benchmark(target))
