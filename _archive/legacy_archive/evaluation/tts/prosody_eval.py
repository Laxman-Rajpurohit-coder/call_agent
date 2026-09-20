import wave
from pathlib import Path
from typing import Any, Dict, List, Optional
import numpy as np


class ProsodyAndFluencyAnalyzer:
    """
    Evaluates speech prosody, voice naturalness, and voice-clunking defects:
    - Speech rate (Words Per Second / WPS)
    - Pitch range & fundamental frequency (F0) estimation
    - Monotonicity / robotic flat-prosody detection
    - Pause placement & duration
    - Voice-clunking defect categorization (C1-C12)
    """

    def __init__(self, target_wps_min: float = 1.6, target_wps_max: float = 3.6):
        self.target_wps_min = target_wps_min
        self.target_wps_max = target_wps_max

    def analyze_prosody(
        self,
        wav_path: str,
        text: str,
        waveform_metrics: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        path = Path(wav_path)
        if not path.exists():
            return {"error": f"File not found: {wav_path}", "passed": False}

        with wave.open(str(path), "rb") as wf:
            framerate = wf.getframerate()
            raw_bytes = wf.readframes(wf.getnframes())

        if len(raw_bytes) == 0:
            return {
                "speech_rate_wps": 0.0,
                "pitch_range_hz": 0.0,
                "monotony_flag": True,
                "clunking_flags": ["C6: Unnatural silence / empty audio"],
                "passed": False,
            }

        samples = np.frombuffer(raw_bytes, dtype=np.int16).astype(np.float32)
        total_duration_s = len(samples) / float(framerate)

        # 1. Speech Rate (WPS)
        words = [w for w in text.split() if w.strip()]
        word_count = len(words)
        effective_duration_s = total_duration_s
        if waveform_metrics:
            leading_s = waveform_metrics.get("leading_silence_ms", 0.0) / 1000.0
            trailing_s = waveform_metrics.get("trailing_silence_ms", 0.0) / 1000.0
            effective_duration_s = max(0.4, total_duration_s - (leading_s + trailing_s))

        speech_rate_wps = round(word_count / effective_duration_s, 2) if effective_duration_s > 0 else 0.0

        # 2. Fundamental Frequency (F0) Estimation via Frame Autocorrelation
        # 30ms windows with 10ms hop
        win_size = int(framerate * 0.030)
        hop_size = int(framerate * 0.010)
        f0_estimates = []

        min_lag = int(framerate / 350.0)  # max F0 ~350Hz
        max_lag = int(framerate / 70.0)   # min F0 ~70Hz

        for start in range(0, len(samples) - win_size, hop_size):
            frame = samples[start : start + win_size]
            fr_energy = np.mean(frame**2)
            if fr_energy < 5000:  # Silence or unvoiced frame
                continue

            # Normalized Autocorrelation
            frame = frame - np.mean(frame)
            autocorr = np.correlate(frame, frame, mode="full")
            autocorr = autocorr[len(frame) - 1 :]
            
            if len(autocorr) > max_lag:
                search_region = autocorr[min_lag:max_lag]
                peak_lag = min_lag + np.argmax(search_region)
                if autocorr[0] > 0 and (autocorr[peak_lag] / autocorr[0]) > 0.35:
                    f0 = framerate / float(peak_lag)
                    if 70.0 <= f0 <= 350.0:
                        f0_estimates.append(f0)

        f0_mean = round(float(np.mean(f0_estimates)), 1) if f0_estimates else 0.0
        f0_std = round(float(np.std(f0_estimates)), 1) if f0_estimates else 0.0
        pitch_min = round(float(np.min(f0_estimates)), 1) if f0_estimates else 0.0
        pitch_max = round(float(np.max(f0_estimates)), 1) if f0_estimates else 0.0
        pitch_range_hz = round(pitch_max - pitch_min, 1)

        # 3. Monotonicity / Robotic Flatness Flag
        # If utterance has >= 8 words and pitch std is very small (< 12Hz)
        monotony_flag = (word_count >= 8 and f0_std < 12.0 and len(f0_estimates) > 20)

        # 4. Energy Variation Across Sentences (RMS variance)
        rms_frame_win = int(framerate * 0.1)  # 100ms
        rms_series = [
            float(np.sqrt(np.mean(samples[i : i + rms_frame_win] ** 2)))
            for i in range(0, len(samples) - rms_frame_win, rms_frame_win)
        ]
        rms_variation_db = round(float(np.std(rms_series)), 1) if rms_series else 0.0

        # 5. Clunking Category Classifier (C1-C12)
        clunking_flags = []
        if waveform_metrics:
            if waveform_metrics.get("click_count", 0) > 0:
                clunking_flags.append(f"C1: Click/pop impulse ({waveform_metrics['click_count']})")
            if waveform_metrics.get("clipping_sample_count", 0) > 0:
                clunking_flags.append(f"C2: Audio clipping ({waveform_metrics['clipping_sample_count']} samples)")
            if waveform_metrics.get("unexpected_gaps_count", 0) > 0:
                clunking_flags.append(f"C6: Unnatural rendering gap (>450ms)")
        
        if monotony_flag:
            clunking_flags.append(f"C7: Robotic monotone (pitch std={f0_std}Hz)")

        if word_count > 3 and (speech_rate_wps < self.target_wps_min or speech_rate_wps > self.target_wps_max):
            clunking_flags.append(f"C10: Out-of-bound speech rate ({speech_rate_wps} WPS)")

        # Prosody Pass Criteria
        passed = (
            len(clunking_flags) == 0 and
            (word_count < 3 or (self.target_wps_min <= speech_rate_wps <= self.target_wps_max))
        )

        return {
            "speech_rate_wps": speech_rate_wps,
            "word_count": word_count,
            "f0_mean_hz": f0_mean,
            "f0_std_hz": f0_std,
            "pitch_range_hz": pitch_range_hz,
            "monotony_flag": monotony_flag,
            "energy_variation": rms_variation_db,
            "clunking_flags": clunking_flags,
            "passed": passed,
        }
