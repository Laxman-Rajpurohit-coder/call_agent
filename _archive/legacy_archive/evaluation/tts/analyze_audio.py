import wave
from pathlib import Path
from typing import Any, Dict, List, Optional
import numpy as np


class AudioWaveformAnalyzer:
    """
    Evaluates raw and telephony audio waveforms for rendering quality:
    - Audio clipping (samples hitting saturation boundaries)
    - Clicks & pops (isolated sample impulse discontinuities)
    - Silence distribution (leading, trailing, and internal silence gaps)
    - Peak amplitude and RMS energy in dBFS
    - Duration and expected duration ratios
    """

    def __init__(
        self,
        clipping_threshold: int = 32760,
        click_delta_threshold: int = 26000,
        silence_threshold_rms: float = 80.0,
        frame_len_ms: int = 20,
    ):
        self.clipping_threshold = clipping_threshold
        self.click_delta_threshold = click_delta_threshold
        self.silence_threshold_rms = silence_threshold_rms
        self.frame_len_ms = frame_len_ms

    def analyze_wav(self, wav_path: str, text: str = "") -> Dict[str, Any]:
        path = Path(wav_path)
        if not path.exists():
            return {
                "error": f"File not found: {wav_path}",
                "passed": False,
            }

        with wave.open(str(path), "rb") as wf:
            n_channels = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            framerate = wf.getframerate()
            n_frames = wf.getnframes()
            raw_bytes = wf.readframes(n_frames)

        if len(raw_bytes) == 0:
            return {
                "audio_duration_ms": 0,
                "clipping_sample_count": 0,
                "click_count": 0,
                "passed": False,
                "failure_reasons": ["empty_audio"],
            }

        samples = np.frombuffer(raw_bytes, dtype=np.int16).astype(np.float32)
        total_duration_ms = round((len(samples) / framerate) * 1000, 1)

        # 1. Clipping detection
        clipping_samples = int(np.sum(np.abs(samples) >= self.clipping_threshold))

        # 2. Clicks & Pops (Impulse delta jumps)
        diffs = np.abs(np.diff(samples))
        click_count = int(np.sum(diffs >= self.click_delta_threshold))

        # 3. Peak and RMS Energy (dBFS)
        peak_val = int(np.max(np.abs(samples))) if len(samples) > 0 else 0
        rms_val = float(np.sqrt(np.mean(samples**2))) if len(samples) > 0 else 0.0
        rms_dbfs = round(20 * np.log10(rms_val / 32768.0 + 1e-9), 2) if rms_val > 0 else -99.0

        # 4. Silence and pause segmentation (20ms frames)
        frame_size = int(framerate * (self.frame_len_ms / 1000.0))
        n_full_frames = len(samples) // frame_size
        frame_energies = []
        for i in range(n_full_frames):
            fr = samples[i * frame_size : (i + 1) * frame_size]
            fr_rms = float(np.sqrt(np.mean(fr**2)))
            frame_energies.append(fr_rms)

        is_silent = [e < self.silence_threshold_rms for e in frame_energies]

        # Leading silence
        leading_silent_frames = 0
        for s in is_silent:
            if s:
                leading_silent_frames += 1
            else:
                break
        leading_silence_ms = round(leading_silent_frames * self.frame_len_ms, 1)

        # Trailing silence
        trailing_silent_frames = 0
        for s in reversed(is_silent):
            if s:
                trailing_silent_frames += 1
            else:
                break
        trailing_silence_ms = round(trailing_silent_frames * self.frame_len_ms, 1)

        # Internal silence gaps
        internal_silent_runs = []
        curr_run = 0
        in_speech = False
        for idx in range(leading_silent_frames, len(is_silent) - trailing_silent_frames):
            if is_silent[idx]:
                curr_run += 1
            else:
                if curr_run > 0:
                    internal_silent_runs.append(curr_run * self.frame_len_ms)
                    curr_run = 0

        internal_silence_count = len(internal_silent_runs)
        max_internal_silence_ms = max(internal_silent_runs) if internal_silent_runs else 0
        unexpected_gaps = sum(1 for gap in internal_silent_runs if gap > 450)

        # 5. Expected duration ratio
        # Rough heuristic: ~13 characters per second for natural TTS
        char_count = len(text)
        expected_dur_ms = max(500.0, (char_count / 13.0) * 1000) if char_count > 0 else total_duration_ms
        duration_ratio = round(total_duration_ms / expected_dur_ms, 2)

        # Rendering failure checks
        failures = []
        if clipping_samples > 0:
            failures.append(f"clipping_detected: {clipping_samples} samples")
        if click_count > 2:
            failures.append(f"clicks_detected: {click_count} impulses")
        if unexpected_gaps > 0:
            failures.append(f"unexpected_rendering_gaps: {unexpected_gaps} gaps > 450ms")
        if total_duration_ms < 200:
            failures.append("audio_too_short")

        passed = len(failures) == 0

        return {
            "audio_duration_ms": total_duration_ms,
            "expected_duration_ms": round(expected_dur_ms, 1),
            "duration_ratio": duration_ratio,
            "sample_rate": framerate,
            "peak_amplitude": peak_val,
            "rms_level": round(rms_val, 1),
            "rms_dbfs": rms_dbfs,
            "clipping_sample_count": clipping_samples,
            "click_count": click_count,
            "leading_silence_ms": leading_silence_ms,
            "trailing_silence_ms": trailing_silence_ms,
            "internal_silence_count": internal_silence_count,
            "internal_silence_max_ms": max_internal_silence_ms,
            "unexpected_gaps_count": unexpected_gaps,
            "passed": passed,
            "failures": failures,
        }
