import argparse
import asyncio
import glob
import json
import os
import subprocess
import time
import wave
from pathlib import Path
from typing import Any, Dict, List, Optional
import numpy as np
from scipy.signal import resample_poly
import yaml

from evaluation.tts.analyze_audio import AudioWaveformAnalyzer
from evaluation.tts.prosody_eval import ProsodyAndFluencyAnalyzer
from evaluation.tts.pronunciation_eval import PronunciationAndEntityEvaluator


async def render_and_evaluate_tts(
    category_filter: Optional[str] = None,
    limit: Optional[int] = None,
    piper_path: str = r".\piper\piper\piper.exe",
    english_model: str = r"models\en_US-lessac-medium.onnx",
    hindi_model: str = r"models\hi_IN-pratham-medium.onnx",
    out_dir: str = "evaluation/tts",
) -> Dict[str, Any]:
    run_id = f"tts-run-{int(time.time())}"
    print(f"\n========================================================")
    print(f"  TTS QUALITY, FLUENCY & CLUNKING EVALUATOR")
    print(f"  Run ID: {run_id}")
    print(f"========================================================\n")

    # 1. Discover Text Cases
    case_files = glob.glob(os.path.join(out_dir, "text_cases", "*.yaml"))
    all_cases: List[Dict[str, Any]] = []
    for cf in case_files:
        with open(cf, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            all_cases.extend(data.get("cases", []))

    if category_filter:
        all_cases = [c for c in all_cases if c.get("category") == category_filter or c.get("id") == category_filter]

    if limit and limit > 0:
        all_cases = all_cases[:limit]

    total_cases = len(all_cases)
    print(f"Discovered {total_cases} TTS test cases to render and analyze.\n")

    waveform_analyzer = AudioWaveformAnalyzer()
    prosody_analyzer = ProsodyAndFluencyAnalyzer()
    pronunciation_eval = PronunciationAndEntityEvaluator()

    results = []
    passed_count = 0

    for idx, item in enumerate(all_cases, start=1):
        case_id = item["id"]
        text = item["text"]
        lang = item.get("language", "en")
        expected_entities = item.get("expected_entities", [])

        case_gen_dir = Path(out_dir) / "generated" / case_id
        case_gen_dir.mkdir(parents=True, exist_ok=True)

        raw_wav_path = str(case_gen_dir / "tts_raw.wav")
        telephony_wav_path = str(case_gen_dir / "tts_telephony.wav")

        model_path = hindi_model if lang == "hi" else english_model

        # 1. Synthesize raw Piper audio (22050Hz)
        t_synth_start = time.perf_counter()
        synth_cmd = f'cmd.exe /c "echo {text} | {piper_path} --model {model_path} --output_file {raw_wav_path}"'
        proc = subprocess.run(synth_cmd, shell=True, capture_output=True)
        synth_latency_ms = round((time.perf_counter() - t_synth_start) * 1000, 1)

        if not os.path.exists(raw_wav_path) or os.path.getsize(raw_wav_path) < 100:
            print(f"[{idx}/{total_cases}] [FAILED] {case_id}: Synthesis failed")
            continue

        # 2. Resample to telephony 8kHz PCM16
        with wave.open(raw_wav_path, "rb") as wf:
            raw_data = wf.readframes(wf.getnframes())
            in_rate = wf.getframerate()
            raw_samples = np.frombuffer(raw_data, dtype=np.int16).astype(np.float32)

        telephony_samples = resample_poly(raw_samples, 8000, in_rate).astype(np.int16)
        telephony_bytes = telephony_samples.tobytes()

        with wave.open(telephony_wav_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(8000)
            wf.writeframes(telephony_bytes)

        # 3. Waveform Analysis
        wave_metrics = waveform_analyzer.analyze_wav(telephony_wav_path, text=text)

        # 4. Prosody & Clunking Analysis
        prosody_metrics = prosody_analyzer.analyze_prosody(telephony_wav_path, text=text, waveform_metrics=wave_metrics)

        # 5. Pronunciation & Entity Verification (via ASR)
        pron_metrics = await pronunciation_eval.evaluate_pronunciation(
            pcm_bytes=telephony_bytes,
            reference_text=text,
            expected_entities=expected_entities,
            language=lang,
        )

        # 6. Overall Pass/Fail Aggregation
        case_passed = (
            wave_metrics.get("passed", False) and
            prosody_metrics.get("passed", False) and
            pron_metrics.get("passed", False)
        )

        if case_passed:
            passed_count += 1
            status_str = "PASSED"
        else:
            status_str = "FLAGGED"

        eval_record = {
            "case_id": case_id,
            "text": text,
            "language": lang,
            "category": item.get("category", "general"),
            "passed": case_passed,
            "synth_latency_ms": synth_latency_ms,
            "waveform": wave_metrics,
            "prosody": prosody_metrics,
            "pronunciation": pron_metrics,
        }

        results.append(eval_record)

        # Save individual analyzed JSON
        analyzed_dir = Path(out_dir) / "analyzed"
        analyzed_dir.mkdir(parents=True, exist_ok=True)
        with open(analyzed_dir / f"{case_id}.json", "w", encoding="utf-8") as jf:
            json.dump(eval_record, jf, indent=2, ensure_ascii=False)

        clunk_str = f" | Clunks: {prosody_metrics.get('clunking_flags')}" if prosody_metrics.get('clunking_flags') else ""
        print(f"[{idx}/{total_cases}] [{status_str}] {case_id:<20} WER={pron_metrics.get('wer')} WPS={prosody_metrics.get('speech_rate_wps')}{clunk_str}")

    print(f"\n========================================================")
    print(f"  TTS EVALUATION COMPLETE")
    print(f"  Clean / Passed: {passed_count}/{total_cases} ({round(passed_count/total_cases*100, 1)}%)")
    print(f"  Flagged for Review: {total_cases - passed_count}/{total_cases}")
    print(f"========================================================\n")

    summary_output = {
        "run_id": run_id,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total_cases": total_cases,
        "passed_count": passed_count,
        "flagged_count": total_cases - passed_count,
        "pass_rate": round(passed_count / float(total_cases), 3) if total_cases > 0 else 0.0,
        "results": results,
    }

    # Save summary report JSON
    rep_dir = Path("evaluation/reports/tts")
    rep_dir.mkdir(parents=True, exist_ok=True)
    with open(rep_dir / f"{run_id}.json", "w", encoding="utf-8") as rf:
        json.dump(summary_output, rf, indent=2, ensure_ascii=False)

    return summary_output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Render & Evaluate TTS Test Suite")
    parser.add_argument("--category", type=str, default=None, help="Filter by category or case ID")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of test cases to run")

    args = parser.parse_args()
    asyncio.run(render_and_evaluate_tts(category_filter=args.category, limit=args.limit))
