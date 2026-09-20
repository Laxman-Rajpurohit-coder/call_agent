import os
import wave
import subprocess
import numpy as np
from scipy.signal import resample_poly

os.makedirs("evaluation/scenarios/barge_in_noise", exist_ok=True)
os.makedirs("evaluation/audio/synthetic", exist_ok=True)

# ── 1. Create Audio Fixtures ─────────────────────────────────────────────────
def create_audio_fixture(text: str, filename_base: str):
    raw_path = f"evaluation/audio/synthetic/{filename_base}_raw.wav"
    out_path = f"evaluation/audio/synthetic/{filename_base}.wav"
    if os.path.exists(out_path):
        return out_path
    
    cmd = f'cmd.exe /c "echo {text} | .\\piper\\piper\\piper.exe --model models\\en_US-lessac-medium.onnx --output_file {raw_path}"'
    subprocess.run(cmd, shell=True, check=True)

    with wave.open(raw_path, "rb") as wf:
        raw = wf.readframes(wf.getnframes())
        rate = wf.getframerate()
        samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32)

    resampled = resample_poly(samples, 8000, rate).astype(np.int16)

    with wave.open(out_path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(8000)
        wf.writeframes(resampled.tobytes())

    return out_path

create_audio_fixture("Actually, tell me the address.", "caller_actually_address_001")
create_audio_fixture("Wait, stop please.", "caller_wait_stop_001")
create_audio_fixture("Can I talk to a human?", "caller_human_transfer_002")

print("Created interruption audio fixtures.")
