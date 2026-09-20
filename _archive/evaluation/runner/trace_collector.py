import json
from pathlib import Path
from time import time
from typing import Any, Dict, Optional


class TraceCollector:
    """
    Standardized event writer emitting chronological JSONL records
    for evaluation runs and scenario analysis.
    """
    def __init__(self, path: str, trace_id: str):
        self.path = Path(path)
        self.trace_id = trace_id
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def emit(self, event: str, **data: Any) -> Dict[str, Any]:
        record = {
            "trace_id": self.trace_id,
            "timestamp_ms": round(time() * 1000),
            "event": event,
            **data,
        }
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        return record
