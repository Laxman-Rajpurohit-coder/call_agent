import os
import sys
import json
import wave
import subprocess
import numpy as np
from faster_whisper import WhisperModel

sys.stdout.reconfigure(encoding='utf-8')

wav_file = r"C:\daily_works\superfone_call\recordings\c780fefe-8fd6-3f96-c07e-2d1490976ced-20260819-113238.wav"
mp4_file = r"C:\daily_works\superfone_call\20260819-0953-09.6463278.mp4"
extracted_audio = r"C:\daily_works\superfone_call\temp_mp4_audio.wav"

print(f"Loading Whisper model...")
model = WhisperModel("tiny", device="cpu", compute_type="int8", cpu_threads=4)

# 1. Analyze Call WAV recording
print(f"\n=======================================================")
print(f"1. ANALYZING CALL WAV RECORDING:")
print(f"   {wav_file}")
print(f"=======================================================")

with wave.open(wav_file, 'rb') as wf:
    dur = wf.getnframes() / wf.getframerate()
    sr = wf.getframerate()
    data = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0

print(f"Duration: {dur:.2f}s | Sample Rate: {sr}Hz | Channels: 1")

segments_hi, _ = model.transcribe(data, beam_size=1, language="hi", vad_filter=True)
print("\n--- Hindi Transcript in Call Recording ---")
for s in segments_hi:
    print(f"  [{s.start:5.1f}s -> {s.end:5.1f}s] {s.text}")

segments_en, _ = model.transcribe(data, beam_size=1, language="en", vad_filter=True)
print("\n--- English Transcript in Call Recording ---")
for s in segments_en:
    print(f"  [{s.start:5.1f}s -> {s.end:5.1f}s] {s.text}")

# 2. Extract audio from MP4 and analyze
print(f"\n=======================================================")
print(f"2. ANALYZING SCREEN RECORDING MP4 VIDEO:")
print(f"   {mp4_file}")
print(f"=======================================================")

cmd = ["ffmpeg", "-y", "-i", mp4_file, "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", extracted_audio]
subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

if os.path.exists(extracted_audio):
    with wave.open(extracted_audio, 'rb') as wf:
        mp4_dur = wf.getnframes() / wf.getframerate()
        mp4_data = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0

    print(f"Video Audio Duration: {mp4_dur:.2f}s")
    vid_segments, _ = model.transcribe(mp4_data, beam_size=1, vad_filter=True)
    print("\n--- Audio Transcript from Screen Recording Video ---")
    for s in vid_segments:
        print(f"  [{s.start:5.1f}s -> {s.end:5.1f}s] {s.text}")
else:
    print("Could not extract audio from MP4.")

print(f"\nAnalysis complete.")
