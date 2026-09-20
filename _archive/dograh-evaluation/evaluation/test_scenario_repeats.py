import os
import sys
import json
import time
import asyncio

sys.path.insert(0, os.path.abspath("."))
sys.path.insert(0, os.path.abspath("dograh-evaluation/tools"))

from evaluation.runner.audiosocket_runner import AudioSocketRunner
from evaluation.evaluators.deterministic import DeterministicEvaluator

async def repeat_scenario_test(repeats: int = 3):
    scenario = {
        "id": "gate_01_normal_inbound",
        "category": "tts_continuity",
        "turns": [{"audio_file": "evaluation/audio/synthetic/caller_no_001.wav"}],
        "required_facts": []
    }

    runner = AudioSocketRunner()
    evaluator = DeterministicEvaluator()

    print(f"\n========================================================")
    print(f"  SCENARIO 1 TRIPLE REPEAT STABILITY TEST")
    print(f"========================================================\n")

    results = []
    for i in range(1, repeats + 1):
        run_id = f"repeat-test-{i}-{int(time.time())}"
        target_dir = f"dograh-evaluation/evaluation/artifacts/repeat_test_{i}"
        os.makedirs(target_dir, exist_ok=True)

        exec_res = await runner.execute_scenario(scenario, run_id=run_id, artifacts_dir=target_dir)
        eval_res = evaluator.evaluate(scenario, exec_res)

        print(f"Run #{i}:")
        print(f"  Caller: '{eval_res.get('caller_transcript')}'")
        print(f"  Agent Text: '{eval_res.get('agent_response')}'")
        print(f"  Audio Duration: {eval_res.get('agent_audio_duration_s')}s")
        print(f"  Passed: {eval_res.get('passed')} (Checks: {eval_res.get('checks')})\n")

        results.append(eval_res)

    all_passed = all(r["passed"] for r in results)
    print(f"Triple Repeat Outcome: {'ALL 3 PASSED' if all_passed else 'SOME FAILED'}\n")
    return results

if __name__ == "__main__":
    asyncio.run(repeat_scenario_test())
