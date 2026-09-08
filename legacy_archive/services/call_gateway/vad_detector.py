import collections
import enum
import time
from typing import Optional, Tuple, Dict, Any
import numpy as np
from scipy.signal import resample_poly
import faster_whisper.vad as fv


class VADState(enum.Enum):
    LISTENING = "LISTENING"
    CONFIRMING_SPEECH = "CONFIRMING_SPEECH"
    IN_SPEECH = "IN_SPEECH"
    POSSIBLE_END = "POSSIBLE_END"


class BargeInState(enum.Enum):
    NORMAL_PLAYBACK = "NORMAL_PLAYBACK"
    BARGE_IN_CANDIDATE = "BARGE_IN_CANDIDATE"
    CONFIRMED_BARGE_IN = "CONFIRMED_BARGE_IN"


from scipy.signal import butter, lfilter


class AudioDSPProcessor:
    """High-Pass Filtering (100Hz) & Speech-Gated Smooth AGC."""
    def __init__(self, sample_rate=8000, target_rms=3500.0, max_gain_db=12.0):
        self.sample_rate = sample_rate
        self.target_rms = target_rms
        self.max_gain = 10.0 ** (max_gain_db / 20.0)
        self.current_gain = 1.0
        b, a = butter(2, 100.0 / (sample_rate / 2.0), btype='high')
        self.b = b
        self.a = a
        self.zi = np.zeros(max(len(a), len(b)) - 1)

    def process(self, samples_int16: np.ndarray) -> np.ndarray:
        if len(samples_int16) == 0:
            return samples_int16
        samples_float = samples_int16.astype(np.float32)
        filtered, self.zi = lfilter(self.b, self.a, samples_float, zi=self.zi)
        current_rms = float(np.sqrt(np.mean(filtered**2)))
        
        # Speech-gated exponential gain smoothing: only adapt gain on active speech (200 RMS)
        if 200.0 < current_rms < self.target_rms:
            target_g = min(self.max_gain, self.target_rms / current_rms)
            self.current_gain = 0.90 * self.current_gain + 0.10 * target_g
        elif current_rms <= 200.0:
            # Decay gain smoothly to 1.0 during silence to avoid noise pumping
            self.current_gain = 0.95 * self.current_gain + 0.05 * 1.0
            
        filtered = filtered * self.current_gain
        return np.clip(filtered, -32768.0, 32767.0).astype(np.int16)


class SileroEndpointingEngine:
    """
    Real-Time Stateful Neural VAD, DSP Filtered & Noise-Tracked Endpointing Engine.
    """
    def __init__(
        self,
        speech_threshold: float = 0.50,
        barge_in_threshold: float = 0.60,
        pre_roll_frames: int = 25,        # 500ms @ 20ms/frame ring buffer
        confirm_frames_needed: int = 2,   # 40ms fast speech confirmation
        hangover_frames_needed: int = 20, # 400ms natural conversational clause endpointing
        barge_in_frames_needed: int = 5,  # 100ms robust barge-in confirmation
        min_utterance_frames: int = 8,    # 160ms min utterance
        max_utterance_frames: int = 750,  # 15.0s max
        echo_correlation_threshold: float = 0.55,
    ):
        self.vad_model = fv.get_vad_model()
        self.speech_threshold = speech_threshold
        self.barge_in_threshold = barge_in_threshold
        self.pre_roll_frames = pre_roll_frames
        self.confirm_frames_needed = confirm_frames_needed
        self.hangover_frames_needed = hangover_frames_needed
        self.barge_in_frames_needed = barge_in_frames_needed
        self.min_utterance_frames = min_utterance_frames
        self.max_utterance_frames = max_utterance_frames
        self.echo_correlation_threshold = echo_correlation_threshold
        self.dsp = AudioDSPProcessor()

        self.state = VADState.LISTENING
        self.barge_in_state = BargeInState.NORMAL_PLAYBACK
        self.pre_roll_buffer = collections.deque(maxlen=pre_roll_frames)
        self.utterance_chunks = []
        self.audio_16k_buffer = np.array([], dtype=np.float32)

        # Agent playback reference buffer (stores recent 1000ms = 50 frames of playback audio)
        self.agent_playback_buffer = collections.deque(maxlen=50)

        # Adaptive ambient noise floor tracker
        self.noise_floor_rms = 150.0
        self.noise_floor_initialized = False

        self.confirm_count = 0
        self.hangover_count = 0
        self.barge_in_count = 0
        self.current_prob = 0.0
        self.last_telemetry: Dict[str, Any] = {}

    def feed_agent_playback(self, frame_pcm16_8k: bytes):
        """Feed agent playback reference frames for echo cross-correlation."""
        if frame_pcm16_8k:
            self.agent_playback_buffer.append(frame_pcm16_8k)

    def reset(self):
        self.state = VADState.LISTENING
        self.barge_in_state = BargeInState.NORMAL_PLAYBACK
        self.pre_roll_buffer.clear()
        self.utterance_chunks.clear()
        self.audio_16k_buffer = np.array([], dtype=np.float32)
        self.confirm_count = 0
        self.hangover_count = 0
        self.barge_in_count = 0
        self.current_prob = 0.0
        self.last_telemetry.clear()

    def _compute_echo_correlation(self, input_samples: np.ndarray) -> float:
        """
        Computes maximum normalized cross-correlation between input frame
        and recent agent playback reference frames.
        """
        if not self.agent_playback_buffer or len(input_samples) == 0:
            return 0.0

        inp_std = np.std(input_samples)
        if inp_std < 1e-4:
            return 0.0
        inp_norm = (input_samples - np.mean(input_samples)) / inp_std

        max_corr = 0.0
        # Check against last 10 playback frames (200ms window)
        recent_playback = list(self.agent_playback_buffer)[-10:]
        for pb_bytes in recent_playback:
            pb_samples = np.frombuffer(pb_bytes, dtype=np.int16).astype(np.float32)
            if len(pb_samples) != len(input_samples):
                continue
            pb_std = np.std(pb_samples)
            if pb_std < 1e-4:
                continue
            pb_norm = (pb_samples - np.mean(pb_samples)) / pb_std
            corr = float(np.mean(inp_norm * pb_norm))
            if corr > max_corr:
                max_corr = corr

        return max(0.0, min(1.0, max_corr))

    def process_frame(
        self,
        frame_pcm16_8k: bytes,
        is_ai_speaking: bool = False
    ) -> Tuple[Optional[str], Optional[bytes], float]:
        """
        Process a single 320-byte (20ms) PCM16 8kHz audio frame with echo-aware gating.
        
        Returns: (event, audio_bytes, prob)
          event: None | "SPEECH_START" | "SPEECH_END" | "BARGE_IN" | "BARGE_IN_CANDIDATE"
          audio_bytes: complete PCM16 8k bytes on SPEECH_END, else None
          prob: Silero speech probability float [0.0 - 1.0]
        """
        if not frame_pcm16_8k or len(frame_pcm16_8k) < 320:
            return None, None, 0.0

        # Convert to int16, process via DSP (High-pass + AGC), then store
        samples_raw = np.frombuffer(frame_pcm16_8k, dtype=np.int16)
        samples_dsp = self.dsp.process(samples_raw)
        frame_pcm16_8k = samples_dsp.tobytes()

        # Always feed continuous pre-roll ring buffer (500ms history)
        self.pre_roll_buffer.append(frame_pcm16_8k)

        # Convert to float32 and compute frame RMS energy
        samples_8k = samples_dsp.astype(np.float32)
        frame_rms = float(np.sqrt(np.mean(samples_8k**2)))
        samples_norm = samples_8k / 32768.0

        # Upsample 8kHz -> 16kHz for Silero VAD
        samples_16k = resample_poly(samples_norm, 2, 1) # 160 samples -> 320 samples @ 16kHz
        self.audio_16k_buffer = np.append(self.audio_16k_buffer, samples_16k)

        # Run Silero VAD when we have at least 512 samples @ 16kHz
        prob = self.current_prob
        while len(self.audio_16k_buffer) >= 512:
            chunk = self.audio_16k_buffer[:512]
            self.audio_16k_buffer = self.audio_16k_buffer[512:]
            out = self.vad_model(chunk)
            prob = float(np.squeeze(out))
            self.current_prob = prob

        # Adaptive Noise Floor Tracking (smooth EMA during non-speech)
        if not is_ai_speaking and prob < 0.30:
            if not self.noise_floor_initialized:
                self.noise_floor_rms = frame_rms
                self.noise_floor_initialized = True
            else:
                self.noise_floor_rms = 0.96 * self.noise_floor_rms + 0.04 * frame_rms

        # ── Case A: AI is currently speaking (Echo-Aware Barge-In Policy) ────
        if is_ai_speaking:
            echo_corr = self._compute_echo_correlation(samples_8k)
            is_echo = (echo_corr >= self.echo_correlation_threshold)

            # Energy gate: require frame energy to exceed ambient noise floor margin
            min_energy_threshold = max(160.0, self.noise_floor_rms * 1.6)
            is_energy_valid = (frame_rms >= min_energy_threshold)

            is_positive_candidate = (
                prob >= self.barge_in_threshold and
                not is_echo and
                is_energy_valid
            )

            # Structured Telemetry
            self.last_telemetry = {
                "event": "barge_in_evaluation",
                "timestamp_ms": int(time.time() * 1000),
                "speech_probability": round(prob, 3),
                "input_rms": round(frame_rms, 1),
                "noise_floor_rms": round(self.noise_floor_rms, 1),
                "echo_correlation": round(echo_corr, 3),
                "is_echo": is_echo,
                "is_energy_valid": is_energy_valid,
                "consecutive_positive_frames": self.barge_in_count,
            }

            if is_positive_candidate:
                self.barge_in_count += 1
                if self.barge_in_count >= self.barge_in_frames_needed:
                    # Confirmed genuine caller speech over agent playback
                    self.barge_in_count = 0
                    self.barge_in_state = BargeInState.CONFIRMED_BARGE_IN
                    self.state = VADState.IN_SPEECH
                    # Seed utterance buffer with full 500ms pre-roll history before interruption
                    self.utterance_chunks = list(self.pre_roll_buffer)
                    self.last_telemetry["decision"] = "confirm_barge_in"
                    return "BARGE_IN", None, prob
                else:
                    self.barge_in_state = BargeInState.BARGE_IN_CANDIDATE
                    self.last_telemetry["decision"] = "candidate_accumulating"
                    return "BARGE_IN_CANDIDATE", None, prob
            else:
                self.barge_in_count = 0
                self.barge_in_state = BargeInState.NORMAL_PLAYBACK
                self.last_telemetry["decision"] = "reject_echo" if is_echo else "reject_noise"
                return None, None, prob

        # ── Case B: Caller is in normal LISTENING / IN_SPEECH state ───────────
        is_speech = (prob >= self.speech_threshold) and (frame_rms >= max(140.0, self.noise_floor_rms * 1.5))

        if self.state == VADState.LISTENING:
            if is_speech:
                self.confirm_count += 1
                if self.confirm_count >= self.confirm_frames_needed:
                    self.state = VADState.IN_SPEECH
                    # Attach 500ms pre-roll ring buffer
                    self.utterance_chunks = list(self.pre_roll_buffer)
                    self.confirm_count = 0
                    self.hangover_count = 0
                    return "SPEECH_START", None, prob
            else:
                self.confirm_count = 0

        elif self.state == VADState.IN_SPEECH:
            self.utterance_chunks.append(frame_pcm16_8k)
            if not is_speech:
                self.state = VADState.POSSIBLE_END
                self.hangover_count = 1
            else:
                self.hangover_count = 0

            # Max duration safety guard
            if len(self.utterance_chunks) >= self.max_utterance_frames:
                full_audio = b"".join(self.utterance_chunks)
                self.reset()
                return "SPEECH_END", full_audio, prob

        elif self.state == VADState.POSSIBLE_END:
            self.utterance_chunks.append(frame_pcm16_8k)
            if is_speech:
                # Speech returned before hangover timeout -> resume IN_SPEECH
                self.state = VADState.IN_SPEECH
                self.hangover_count = 0
            else:
                self.hangover_count += 1
                if self.hangover_count >= self.hangover_frames_needed:
                    # Trailing silence confirmed -> SPEECH_END
                    full_audio = b"".join(self.utterance_chunks)
                    frames_count = len(self.utterance_chunks)
                    self.reset()
                    if frames_count >= self.min_utterance_frames:
                        return "SPEECH_END", full_audio, prob
                    else:
                        # Too short (<200ms) -> discard noise click
                        return None, None, prob

        return None, None, prob
