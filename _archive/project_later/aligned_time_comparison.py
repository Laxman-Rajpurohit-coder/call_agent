import os
import sys
import wave
import numpy as np
from faster_whisper import WhisperModel

sys.stdout.reconfigure(encoding='utf-8')

wav_file = r"C:\daily_works\superfone_call\recordings\9b940774-2621-aa33-9b1a-6dca43d0a495-20260820-050304.wav"
mp4_audio = r"C:\daily_works\superfone_call\temp_conv_mp4_audio.wav"

with wave.open(wav_file, 'rb') as wf:
    sr = wf.getframerate()
    wav_data = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16)

with wave.open(mp4_audio, 'rb') as wf:
    mp4_sr = wf.getframerate()
    mp4_data = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16)

offset_sec = 63.0
offset_samples = int(offset_sec * sr)

# Slice 63s onwards from Asterisk WAV
sliced_wav = wav_data[offset_samples : offset_samples + len(mp4_data)]

print(f"=== Aligned Comparison: Asterisk WAV (from 63.0s) vs MP4 Video (0.0s to 76.5s) ===")
print(f"Asterisk Sliced Duration: {len(sliced_wav)/sr:.2f}s | MP4 Duration: {len(mp4_data)/mp4_sr:.2f}s\n")

print(f"{'Time in Video':<15} | {'Asterisk WAV Time':<18} | {'Asterisk MixMon RMS':<20} | {'MP4 Video Mic RMS'}")
print(f"{'-'*15}-+-{'-'*18}-+-{'-'*20}-+-{'-'*20}")

for t in range(0, min(int(len(mp4_data)/mp4_sr), 76), 4):
    m_chunk = mp4_data[t*mp4_sr : (t+4)*mp4_sr]
    m_rms = int(np.sqrt(np.mean(m_chunk.astype(np.float64)**2))) if len(m_chunk) > 0 else 0
    m_max = np.max(np.abs(m_chunk)) if len(m_chunk) > 0 else 0
    
    w_chunk = sliced_wav[t*sr : (t+4)*sr]
    w_rms = int(np.sqrt(np.mean(w_chunk.astype(np.float64)**2))) if len(w_chunk) > 0 else 0
    w_max = np.max(np.abs(w_chunk)) if len(w_chunk) > 0 else 0
    
    print(f"{t:02d}s - {t+4:02d}s (video) | {t+63:02d}s - {t+67:02d}s (call) | RMS={w_rms:5d}, Peak={w_max:5d}  | RMS={m_rms:5d}, Peak={m_max:5d}")
