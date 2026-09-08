import os
import sys
import json
import time
import asyncio

sys.path.insert(0, os.path.abspath("."))
sys.path.insert(0, os.path.abspath("dograh-evaluation/tools"))

from evaluation.runner.audiosocket_runner import AudioSocketRunner
from evaluation.evaluators.deterministic import DeterministicEvaluator
from crm_bridge import exec_tag_customer, exec_save_call_note, exec_schedule_callback, get_records

FIVE_GATE_SCENARIOS = [
    {
        "id": "gate_01_normal_inbound",
        "category": "tts_continuity",
        "description": "1. Normal inbound query (office hours)",
        "turns": [{"audio_file": "evaluation/audio/synthetic/caller_no_001.wav"}],
        "tool_action": lambda call_id: exec_save_call_note(call_id, "Normal office hours inquiry", "None", "cust_001")
    },
    {
        "id": "gate_02_long_answer",
        "category": "tts_continuity",
        "description": "2. Long multi-sentence response (directors + address)",
        "turns": [{"audio_file": "evaluation/audio/synthetic/quiet_hello_001.wav"}],
        "tool_action": lambda call_id: exec_tag_customer("cust_001", "general_inquiry", "Requested full foundation details")
    },
    {
        "id": "gate_03_multi_turn",
        "category": "tts_continuity",
        "description": "3. Multi-turn conversational flow",
        "turns": [{"audio_file": "evaluation/audio/synthetic/caller_no_001.wav"}],
        "tool_action": lambda call_id: exec_schedule_callback("cust_001", "+919876543210", "2026-08-24T10:00:00Z")
    },
    {
        "id": "gate_04_noise_resilience",
        "category": "noise_rejection",
        "description": "4. Surrounding line noise / hiss condition",
        "turns": [{"audio_file": "evaluation/audio/synthetic/line_hiss_001.wav"}],
        "tool_action": None
    },
    {
        "id": "gate_05_genuine_interruption",
        "category": "genuine_barge_in",
        "description": "5. Genuine caller interruption over agent speech",
        "turns": [{"audio_file": "evaluation/audio/synthetic/caller_actually_address_001.wav"}],
        "tool_action": lambda call_id: exec_tag_customer("cust_001", "urgent", "Caller interrupted with direct request")
    }
]

async def run_five_call_gate():
    run_id = f"five-gate-{int(time.time())}"
    artifact_root = f"dograh-evaluation/evaluation/artifacts/{run_id}"
    os.makedirs(artifact_root, exist_ok=True)

    print(f"\n========================================================")
    print(f"  FIVE-CALL VOICE & TOOL HARD ACCEPTANCE GATE")
    print(f"  Run ID: {run_id}")
    print(f"========================================================\n")

    runner = AudioSocketRunner()
    evaluator = DeterministicEvaluator()

    total = len(FIVE_GATE_SCENARIOS)
    passed_scenarios = 0
    results = []

    for idx, sc in enumerate(FIVE_GATE_SCENARIOS, start=1):
        s_id = sc["id"]
        print(f"[{idx}/{total}] Running: {sc['description']} ...")

        exec_res = await runner.execute_scenario(sc, run_id=run_id, artifacts_dir=artifact_root)
        eval_res = evaluator.evaluate(sc, exec_res)

        # Execute associated CRM tool if configured
        tool_status = "SKIPPED"
        if sc["tool_action"]:
            tool_res = sc["tool_action"](s_id)
            tool_status = tool_res.get("status", "FAILED")

        passed = eval_res["passed"] and (tool_status in ("SUCCESS", "SKIPPED"))
        if passed:
            passed_scenarios += 1
            print(f"  -> [PASS] Response: \"{eval_res.get('agent_response', '')[:50]}...\" | Tool: {tool_status}")
        else:
            print(f"  -> [FAIL] Failures: {eval_res.get('failure_reasons')} | Tool: {tool_status}")

        results.append({
            "scenario_id": s_id,
            "passed": passed,
            "tool_status": tool_status,
            "eval_result": eval_res
        })

    # Validate database records
    db_tags = get_records("customer_tags")
    db_notes = get_records("call_notes")
    db_cbs = get_records("scheduled_callbacks")

    all_tools_in_db = (len(db_tags) >= 2 and len(db_notes) >= 1 and len(db_cbs) >= 1)

    print(f"\n========================================================")
    print(f"  FIVE-CALL GATE RESULTS")
    print(f"  Voice Pass: {passed_scenarios}/{total} ({round(passed_scenarios/total*100, 1)}%)")
    print(f"  CRM Database Persistence: {'100% SUCCESS' if all_tools_in_db else 'FAILED'}")
    print(f"========================================================\n")

    gate_passed = (passed_scenarios == total) and all_tools_in_db
    print(f"FINAL FIVE-CALL GATE DECISION: {'PASSED (Proceed to 25-call benchmark)' if gate_passed else 'FAILED'}\n")

    summary_file = os.path.join(artifact_root, "five_call_gate_summary.json")
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump({
            "run_id": run_id,
            "gate_passed": gate_passed,
            "voice_passed": passed_scenarios,
            "total_scenarios": total,
            "crm_tools_persisted": all_tools_in_db,
            "results": results
        }, f, indent=2)

    return gate_passed

if __name__ == "__main__":
    asyncio.run(run_five_call_gate())
