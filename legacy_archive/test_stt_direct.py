import faster_whisper
import wave
import numpy as np
import time
from scipy.signal import resample_poly

model = faster_whisper.WhisperModel("base.en", device="cpu", compute_type="int8")
wf = wave.open(r'C:\daily_works\superfone_call\recordings\9b940774-2621-aa33-9b1a-6dca43d0a495-20260820-050304.wav', 'rb')
wf.setpos(12 * 8000)
raw = wf.readframes(2 * 8000)
wf.close()

samples = np.frombuffer(raw, dtype=np.int16)
samples_16k = resample_poly(samples, 2, 1)
audio_float32 = samples_16k.astype(np.float32) / 32768.0

t0 = time.perf_counter()
segments, _ = model.transcribe(audio_float32, beam_size=1, vad_filter=False, temperature=0.0)
text = ''.join([s.text for s in segments]).strip()
lat = (time.perf_counter() - t0) * 1000.0
print(f'Whisper transcribed in {lat:.1f}ms: "{text}"')
