import os
import wave
import json
import time
from typing import Dict, Any, Optional
import numpy as np

class AudioStageLogger:
    """
    Captures multi-stage audio artifacts to isolate playback vs synthesis defects:
      1. tts_raw.wav (raw Piper output)
      2. tts_telephony.wav (resampled 8kHz PCM16)
      3. agent_playback.wav (actual streamed/received audio)
      4. agent_reference.wav (echo cancellation buffer)
      5. events.jsonl (frame-level telemetry)
    """
    def __init__(self, run_dir: str):
        self.run_dir = run_dir
        os.makedirs(run_dir, exist_ok=True)
        self.events_file = os.path.join(run_dir, "events.jsonl")

    def log_event(self, event_name: str, payload: Dict[str, Any]):
        entry = {
            "timestamp_ms": int(time.time() * 1000),
            "event": event_name,
            **payload
        }
        with open(self.events_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    def save_wav(self, filename: str, pcm_data: bytes, sample_rate: int = 8000, channels: int = 1):
        filepath = os.path.join(self.run_dir, filename)
        with wave.open(filepath, "wb") as wf:
            wf.setnchannels(channels)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(pcm_data)
        return filepath

    def compute_metrics(
        self,
        tts_gen_ms: float,
        tts_audio_pcm: bytes,
        playback_audio_pcm: bytes,
        underflow_count: int = 0,
        gap_count: int = 0
    ) -> Dict[str, Any]:
        audio_dur_s = len(tts_audio_pcm) / (8000.0 * 2)
        audio_dur_ms = audio_dur_s * 1000.0
        rtf = (tts_gen_ms / audio_dur_ms) if audio_dur_ms > 0 else 0.0

        metrics = {
            "tts_generation_duration_ms": round(tts_gen_ms, 2),
            "tts_audio_duration_ms": round(audio_dur_ms, 2),
            "playback_audio_duration_ms": round(len(playback_audio_pcm) / (8000.0 * 2) * 1000.0, 2),
            "realtime_factor": round(rtf, 4),
            "queue_underflow_count": underflow_count,
            "unexpected_gap_count": gap_count,
            "is_sustainable_realtime": (rtf < 0.35)
        }
        self.log_event("stage_metrics", metrics)
        return metrics
