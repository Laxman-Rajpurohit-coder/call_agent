import argparse
import asyncio
import glob
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml

from evaluation.evaluators.deterministic import DeterministicEvaluator
from evaluation.runner.audiosocket_runner import AudioSocketRunner


async def run_evaluation(
    scenario_id: Optional[str] = None,
    suite: str = "smoke",
    transport: str = "direct_audiosocket",
    config_path: str = "evaluation/configs/baseline.json",
    output_dir: str = "evaluation/artifacts",
):
    run_id = f"run-{int(time.time())}"
    print(f"\n========================================================")
    print(f"  AUTOMATED VOICE EVALUATION HARNESS")
    print(f"  Run ID: {run_id}")
    print(f"  Transport: {transport}")
    print(f"  Config: {config_path}")
    print(f"========================================================\n")

    # Discover scenarios
    scenarios_dir = Path("evaluation/scenarios") / suite
    if scenario_id:
        scenario_files = [scenarios_dir / f"{scenario_id}.yaml"]
    else:
        scenario_files = list(scenarios_dir.glob("*.yaml"))

    if not scenario_files or not scenario_files[0].exists():
        print(f"[ERROR] No scenario files found in {scenarios_dir} matching query.")
        sys.exit(1)

    runner = AudioSocketRunner()
    evaluator = DeterministicEvaluator()

    total_scenarios = len(scenario_files)
    passed_count = 0
    results = []

    for idx, sf in enumerate(scenario_files, start=1):
        with open(sf, "r", encoding="utf-8") as f:
            scenario_data = yaml.safe_load(f)

        s_id = scenario_data.get("id", sf.stem)
        print(f"[{idx}/{total_scenarios}] Running scenario: {s_id} ...")

        exec_res = await runner.execute_scenario(scenario_data, run_id=run_id, artifacts_dir=output_dir)
        eval_res = evaluator.evaluate(scenario_data, exec_res)

        status_str = "PASSED" if eval_res["passed"] else "FAILED"
        if eval_res["passed"]:
            passed_count += 1
            print(f"  -> [{status_str}] Response: \"{eval_res.get('agent_response', '')[:80]}...\"")
        else:
            print(f"  -> [{status_str}] Failures: {eval_res.get('failure_reasons')}")

        results.append(eval_res)

    print(f"\n========================================================")
    print(f"  EVALUATION RESULTS SUMMARY")
    print(f"  Passed: {passed_count}/{total_scenarios} ({round(passed_count/total_scenarios*100, 1)}%)")
    print(f"  Artifacts saved to: {Path(output_dir) / run_id}")
    print(f"========================================================\n")

    # Generate summary JSON report
    report_dir = Path("evaluation/reports/generated")
    report_dir.mkdir(parents=True, exist_ok=True)
    summary_data = {
        "run_id": run_id,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "suite": suite,
        "transport": transport,
        "total": total_scenarios,
        "passed": passed_count,
        "failed": total_scenarios - passed_count,
        "pass_rate": round(passed_count / total_scenarios, 3),
        "results": results,
    }
    with open(report_dir / f"{suite}_{run_id}.json", "w", encoding="utf-8") as rf:
        json.dump(summary_data, rf, indent=2)

    return summary_data


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Automated Voice Evaluation Harness")
    parser.add_argument("--scenario", type=str, default=None, help="Specific scenario ID (e.g. foundation_address_001)")
    parser.add_argument("--suite", type=str, default="smoke", help="Scenario suite (default: smoke)")
    parser.add_argument("--transport", type=str, default="direct_audiosocket", help="Transport mode")
    parser.add_argument("--config", type=str, default="evaluation/configs/baseline.json", help="Baseline config path")
    parser.add_argument("--output", type=str, default="evaluation/artifacts", help="Artifacts output directory")

    args = parser.parse_args()
    asyncio.run(
        run_evaluation(
            scenario_id=args.scenario,
            suite=args.suite,
            transport=args.transport,
            config_path=args.config,
            output_dir=args.output,
        )
    )
