import os
import sys
import wave
import numpy as np
from services.tts.kokoro_engine import KokoroTTSEngine

art_dir = r"C:\Users\msanj\.gemini\antigravity\brain\3f670608-a148-48ef-8f33-27bc120319d4"
out_wav = os.path.join(art_dir, "kokoro_human_sample.wav")

text = "Hello, welcome to Malisaini Samaj Seva Foundation. How can I help you today?"

print(f"Initializing Kokoro-82M TTS Engine...")
engine = KokoroTTSEngine()

if not engine.kokoro:
    print("[ERROR] Kokoro model not ready yet.")
    sys.exit(1)

print(f"Synthesizing: '{text}'...")
audio_bytes = engine.synthesize_telephony_8k(text, voice="af_sarah")

with wave.open(out_wav, "wb") as wf:
    wf.setnchannels(1)
    wf.setsampwidth(2)
    wf.setframerate(8000)
    wf.writeframes(audio_bytes)

dur_s = len(audio_bytes) / 16000.0
print(f"[SUCCESS] Saved Kokoro sample to {out_wav} ({dur_s:.2f}s, {len(audio_bytes)} bytes)")
