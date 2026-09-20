import os
import json
import glob
from typing import List, Dict, Any
from services.dashboard.app.config import settings

def get_evaluation_reports() -> List[Dict[str, Any]]:
    reports_dir = settings.EVAL_REPORTS_DIR
    if not os.path.exists(reports_dir):
        return []

    pattern = os.path.join(reports_dir, "*.json")
    files = glob.glob(pattern)
    reports = []
    
    for fpath in files:
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
                reports.append({
                    "filename": os.path.basename(fpath),
                    "run_id": data.get("run_id", ""),
                    "timestamp": data.get("timestamp", ""),
                    "suite": data.get("suite", ""),
                    "transport": data.get("transport", ""),
                    "total": data.get("total", 0),
                    "passed": data.get("passed", 0),
                    "failed": data.get("failed", 0),
                    "pass_rate": data.get("pass_rate", 0.0),
                    "results_count": len(data.get("results", []))
                })
        except Exception:
            pass

    reports.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    return reports

def get_evaluation_detail(run_id: str) -> Dict[str, Any]:
    reports_dir = settings.EVAL_REPORTS_DIR
    pattern = os.path.join(reports_dir, f"*{run_id}*.json")
    files = glob.glob(pattern)
    if not files:
        return {}
    
    with open(files[0], "r", encoding="utf-8") as f:
        return json.load(f)
