import os
import sys
import wave
import subprocess
import numpy as np
from faster_whisper import WhisperModel

sys.stdout.reconfigure(encoding='utf-8')

wav_file = r"C:\daily_works\superfone_call\recordings\9b940774-2621-aa33-9b1a-6dca43d0a495-20260820-050304.wav"
mp4_file = r"C:\daily_works\superfone_call\20260819-0953-09.6463278.mp4"
extracted_audio = r"C:\daily_works\superfone_call\temp_conv_mp4_audio.wav"

print(f"Loading Whisper model...")
model = WhisperModel("tiny", device="cpu", compute_type="int8", cpu_threads=4)

# 1. Analyze Call WAV recording
print(f"\n=======================================================")
print(f"1. ANALYZING LATEST CONVERSATIONAL CALL WAV:")
print(f"   {wav_file}")
print(f"=======================================================")

with wave.open(wav_file, 'rb') as wf:
    dur = wf.getnframes() / wf.getframerate()
    sr = wf.getframerate()
    data = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16)
    float_data = data.astype(np.float32) / 32768.0

print(f"Duration: {dur:.2f}s | Sample Rate: {sr}Hz | RMS: {np.sqrt(np.mean(data.astype(np.float64)**2)):.1f} | Peak: {np.max(np.abs(data))}")

segments, _ = model.transcribe(float_data, beam_size=1, vad_filter=False)
print("\n--- Transcript in Call Recording (Asterisk MixMonitor) ---")
for s in segments:
    print(f"  [{s.start:5.1f}s -> {s.end:5.1f}s] {s.text}")

# 2. Extract audio from MP4 and analyze
print(f"\n=======================================================")
print(f"2. ANALYZING NEW SCREEN RECORDING MP4 VIDEO:")
print(f"   {mp4_file}")
print(f"=======================================================")

cmd = ["ffmpeg", "-y", "-i", mp4_file, "-vn", "-acodec", "pcm_s16le", "-ar", "8000", "-ac", "1", extracted_audio]
subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

if os.path.exists(extracted_audio):
    with wave.open(extracted_audio, 'rb') as wf:
        mp4_dur = wf.getnframes() / wf.getframerate()
        mp4_data = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16)
        mp4_float = mp4_data.astype(np.float32) / 32768.0

    print(f"Video Audio Duration: {mp4_dur:.2f}s | RMS: {np.sqrt(np.mean(mp4_data.astype(np.float64)**2)):.1f} | Peak: {np.max(np.abs(mp4_data))}")
    vid_segments, _ = model.transcribe(mp4_float, beam_size=1, vad_filter=False)
    print("\n--- Audio Transcript from Screen Recording Video (Microphone) ---")
    for s in vid_segments:
        print(f"  [{s.start:5.1f}s -> {s.end:5.1f}s] {s.text}")
else:
    print("Could not extract audio from MP4.")

print(f"\nCross-analysis complete.")
