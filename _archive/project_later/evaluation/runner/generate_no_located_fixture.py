import wave
import subprocess
import numpy as np
from scipy.signal import resample_poly

raw_wav = "evaluation/audio/synthetic/caller_no_where_located_001_raw.wav"
out_wav = "evaluation/audio/synthetic/caller_no_where_located_001.wav"

cmd = f'cmd.exe /c "echo No, where is the office located? | .\\piper\\piper\\piper.exe --model models\\en_US-lessac-medium.onnx --output_file {raw_wav}"'
subprocess.run(cmd, shell=True, check=True)

with wave.open(raw_wav, "rb") as wf:
    raw = wf.readframes(wf.getnframes())
    rate = wf.getframerate()
    samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32)

resampled = resample_poly(samples, 8000, rate).astype(np.int16)

with wave.open(out_wav, "wb") as wf:
    wf.setnchannels(1)
    wf.setsampwidth(2)
    wf.setframerate(8000)
    wf.writeframes(resampled.tobytes())

print("Created caller_no_where_located_001.wav fixture.")
