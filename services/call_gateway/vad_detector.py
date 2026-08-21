import collections
import enum
import time
import numpy as np
from scipy.signal import resample_poly
import faster_whisper.vad as fv

class VADState(enum.Enum):
    LISTENING = "LISTENING"
    CONFIRMING_SPEECH = "CONFIRMING_SPEECH"
    IN_SPEECH = "IN_SPEECH"
    POSSIBLE_END = "POSSIBLE_END"

class SileroEndpointingEngine:
    """
    Real-Time Stateful Neural VAD & Endpointing Engine.
    
    Combines:
      - Silero VAD (ONNX) neural voice probability
      - 300ms pre-roll ring buffer (15 frames x 20ms)
      - 120ms speech-start confirmation (6 consecutive speech frames)
      - 400ms hangover trailing silence (20 consecutive non-speech frames)
      - Separate 200ms sustained barge-in threshold for AI_SPEAKING state
      - Min utterance threshold (400ms) to discard brief clicks/breaths
    """
    def __init__(
        self,
        speech_threshold: float = 0.45,
        barge_in_threshold: float = 0.52,
        pre_roll_frames: int = 25,        # 500ms @ 20ms/frame ring buffer
        confirm_frames_needed: int = 3,   # 60ms fast speech confirmation
        hangover_frames_needed: int = 20, # 400ms natural conversational clause endpointing
        barge_in_frames_needed: int = 4,  # 80ms fast & reliable barge-in confirmation
        min_utterance_frames: int = 10,   # 200ms min utterance
        max_utterance_frames: int = 750,  # 15.0s max
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

        self.state = VADState.LISTENING
        self.pre_roll_buffer = collections.deque(maxlen=pre_roll_frames)
        self.utterance_chunks = []
        self.audio_16k_buffer = np.array([], dtype=np.float32)

        self.confirm_count = 0
        self.hangover_count = 0
        self.barge_in_count = 0
        self.current_prob = 0.0

    def reset(self):
        self.state = VADState.LISTENING
        self.pre_roll_buffer.clear()
        self.utterance_chunks.clear()
        self.audio_16k_buffer = np.array([], dtype=np.float32)
        self.confirm_count = 0
        self.hangover_count = 0
        self.barge_in_count = 0
        self.current_prob = 0.0

    def process_frame(self, frame_pcm16_8k: bytes, is_ai_speaking: bool = False):
        """
        Process a single 320-byte (20ms) PCM16 8kHz audio frame.
        
        Returns: (event, audio_bytes, prob)
          event: None | "SPEECH_START" | "SPEECH_END" | "BARGE_IN"
          audio_bytes: complete PCM16 8k bytes on SPEECH_END, else None
          prob: Silero speech probability float [0.0 - 1.0]
        """
        if not frame_pcm16_8k or len(frame_pcm16_8k) < 320:
            return None, None, 0.0

        # Always feed continuous pre-roll ring buffer (500ms history)
        self.pre_roll_buffer.append(frame_pcm16_8k)

        # Convert to float32 and upsample 8kHz -> 16kHz
        samples_8k = np.frombuffer(frame_pcm16_8k, dtype=np.int16).astype(np.float32) / 32768.0
        samples_16k = resample_poly(samples_8k, 2, 1) # 160 samples -> 320 samples @ 16kHz
        self.audio_16k_buffer = np.append(self.audio_16k_buffer, samples_16k)

        # Run Silero VAD when we have at least 512 samples @ 16kHz
        prob = self.current_prob
        while len(self.audio_16k_buffer) >= 512:
            chunk = self.audio_16k_buffer[:512]
            self.audio_16k_buffer = self.audio_16k_buffer[512:]
            out = self.vad_model(chunk)
            prob = float(np.squeeze(out))
            self.current_prob = prob

        # ── Case A: AI is currently speaking (Barge-In Policy) ───────────────
        if is_ai_speaking:
            if prob >= self.barge_in_threshold:
                self.barge_in_count += 1
                if self.barge_in_count >= self.barge_in_frames_needed:
                    self.barge_in_count = 0
                    self.state = VADState.IN_SPEECH
                    # Seed utterance buffer with the full 500ms pre-roll history before barge-in
                    self.utterance_chunks = list(self.pre_roll_buffer)
                    return "BARGE_IN", None, prob
            else:
                self.barge_in_count = 0
            return None, None, prob

        # ── Case B: Caller is in normal LISTENING / IN_SPEECH state ───────────
        is_speech = prob >= self.speech_threshold

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
                        # Too short (<400ms) -> discard without triggering STT
                        return None, None, prob

        return None, None, prob
