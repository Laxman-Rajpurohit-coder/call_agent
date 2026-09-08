import os
import json
import glob
from typing import List, Dict, Any
from services.dashboard.app.config import settings

def get_load_test_summaries() -> List[Dict[str, Any]]:
    load_dir = settings.LOAD_TESTS_DIR
    pattern = os.path.join(load_dir, "load_test_*.json")
    files = glob.glob(pattern)
    results = []

    for fpath in files:
        fname = os.path.basename(fpath)
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
                summary = data.get("summary", {})
                results.append({
                    "filename": fname,
                    "concurrency": data.get("concurrency", 0),
                    "total_elapsed_ms": data.get("total_elapsed_ms", 0),
                    "total_calls": summary.get("total_calls", 0),
                    "accepted": summary.get("accepted", 0),
                    "rejected": summary.get("rejected", 0),
                    "succeeded": summary.get("succeeded", 0),
                    "stt_p50": summary.get("stt_queue_wait_p50_ms", 0.0),
                    "stt_p95": summary.get("stt_queue_wait_p95_ms", 0.0),
                    "llm_lock_p50": summary.get("llm_lock_wait_p50_ms", 0.0),
                    "llm_lock_p95": summary.get("llm_lock_wait_p95_ms", 0.0),
                    "tts_p50": summary.get("tts_queue_wait_p50_ms", 0.0),
                    "tts_p95": summary.get("tts_queue_wait_p95_ms", 0.0),
                })
        except Exception:
            pass

    results.sort(key=lambda x: x.get("concurrency", 0))
    return results
