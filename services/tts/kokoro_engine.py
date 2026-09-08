import os
import re
import numpy as np
from scipy.signal import resample_poly

# Ensure np.load allows loading the voices dictionary archive
_orig_load = np.load
np.load = lambda *args, **kwargs: _orig_load(*args, **{**kwargs, 'allow_pickle': True})

from kokoro_onnx import Kokoro

MODELS_DIR = r"c:\daily_works\superfone_call\models"
KOKORO_MODEL_PATH = os.path.join(MODELS_DIR, "kokoro-v0_19.onnx")
KOKORO_VOICES_PATH = os.path.join(MODELS_DIR, "voices.bin")

class KokoroTTSEngine:
    def __init__(self, model_path: str = KOKORO_MODEL_PATH, voices_path: str = KOKORO_VOICES_PATH):
        self.model_path = model_path
        self.voices_path = voices_path
        self.kokoro = None
        self.default_voice = "af_sarah"
        self._init_engine()

    def _init_engine(self):
        if not os.path.exists(self.model_path) or not os.path.exists(self.voices_path):
            print(f"[Kokoro] Weights not yet present at {self.model_path}")
            return
        try:
            self.kokoro = Kokoro(self.model_path, self.voices_path)
            print(f"[Kokoro] Initialized Kokoro-82M ONNX model successfully.")
        except Exception as ex:
            print(f"[Kokoro] Initialization error: {ex}")

    def synthesize_telephony_8k(self, text: str, voice: str = "af_sarah", speed: float = 1.0) -> bytes:
        """
        Synthesizes text via Kokoro at 24kHz and converts cleanly to 8kHz PCM16 mono
        using exact 3x integer decimation (resample_poly 1, 3).
        """
        if self.kokoro is None:
            self._init_engine()
            if self.kokoro is None:
                raise RuntimeError("Kokoro engine weights not available")

        # Determine language code & dynamic voice profile
        is_hindi = bool(re.search(r'[\u0900-\u097F]', text))
        lang_code = "hi" if is_hindi else "en-us"
        
        VOICE_MAP = {
            "hi_pratham": "am_adam",
            "hi_female": "af_bella",
            "deepgram_aura_asteria": "af_bella",
            "deepgram_aura_zeus": "am_adam",
            "deepgram_aura_orion": "bm_george",
            "cartesia_hindi_female": "af_sky",
            "af_sarah": "af_sarah",
            "af_bella": "af_bella",
            "af_nicole": "af_nicole",
            "af_sky": "af_sky",
            "am_adam": "am_adam",
            "am_michael": "am_michael",
            "bf_emma": "bf_emma",
            "bm_george": "bm_george",
            "bm_fable": "bm_fable"
        }
        voice_to_use = VOICE_MAP.get(voice, "af_bella")

        # Generate 24kHz float32 audio
        samples_24k, sample_rate = self.kokoro.create(
            text,
            voice=voice_to_use,
            speed=speed,
            lang=lang_code
        )

        if samples_24k is None or len(samples_24k) == 0:
            return b""

        # Lossless 3x Integer Decimation: 24,000 Hz -> 8,000 Hz
        samples_8k = resample_poly(samples_24k, 1, 3)

        # Scale float [-1.0, 1.0] to int16 [-32767, 32767]
        samples_int16 = np.clip(samples_8k * 32767.0, -32767.0, 32767.0).astype(np.int16)
        return samples_int16.tobytes()

    def synthesize_hd_24k(self, text: str, voice: str = "af_sarah", speed: float = 1.0) -> bytes:
        """
        Synthesizes 24kHz Ultra-HD studio-quality natural female voice (no telephony compression).
        Returns 24000Hz 16-bit PCM mono audio bytes.
        """
        if self.kokoro is None:
            self._init_engine()
            if self.kokoro is None:
                raise RuntimeError("Kokoro engine weights not available")

        is_hindi = bool(re.search(r'[\u0900-\u097F]', text))
        lang_code = "hi" if is_hindi else "en-us"
        voice_to_use = voice if voice else "af_sarah"

        samples_24k, sample_rate = self.kokoro.create(
            text,
            voice=voice_to_use,
            speed=speed,
            lang=lang_code
        )

        if samples_24k is None or len(samples_24k) == 0:
            return b""

        samples_int16 = np.clip(samples_24k * 32767.0, -32767.0, 32767.0).astype(np.int16)
        return samples_int16.tobytes()

if __name__ == "__main__":
    engine = KokoroTTSEngine()
    if engine.kokoro:
        pcm = engine.synthesize_telephony_8k("Hello! Welcome to Malisaini Samaj Seva Foundation.")
        print(f"Synthesized {len(pcm)} bytes of 8kHz telephony audio via Kokoro!")
