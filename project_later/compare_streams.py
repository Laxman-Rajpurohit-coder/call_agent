import os
import sys
import wave
import subprocess
import numpy as np

sys.stdout.reconfigure(encoding='utf-8')

wav_file = r"C:\daily_works\superfone_call\recordings\c780fefe-8fd6-3f96-c07e-2d1490976ced-20260819-113238.wav"
mp4_file = r"C:\daily_works\superfone_call\20260819-0953-09.6463278.mp4"
extracted_audio = r"C:\daily_works\superfone_call\temp_mp4_audio.wav"

# 1. Extract audio from MP4 if not done
if not os.path.exists(extracted_audio) or os.path.getsize(extracted_audio) < 1000:
    cmd = ["ffmpeg", "-y", "-i", mp4_file, "-vn", "-acodec", "pcm_s16le", "-ar", "8000", "-ac", "1", extracted_audio]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

with wave.open(wav_file, 'rb') as wf:
    wav_sr = wf.getframerate()
    wav_n = wf.getnframes()
    wav_data = np.frombuffer(wf.readframes(wav_n), dtype=np.int16)

with wave.open(extracted_audio, 'rb') as wf:
    mp4_sr = wf.getframerate()
    mp4_n = wf.getnframes()
    mp4_data = np.frombuffer(wf.readframes(mp4_n), dtype=np.int16)

print(f"=== Audio Analysis: Call WAV vs MP4 Video ===")
print(f"Call WAV (Asterisk): {len(wav_data)/wav_sr:.2f}s | RMS: {np.sqrt(np.mean(wav_data.astype(np.float64)**2)):.1f} | Peak: {np.max(np.abs(wav_data))}")
print(f"MP4 Video (Local Mic): {len(mp4_data)/mp4_sr:.2f}s | RMS: {np.sqrt(np.mean(mp4_data.astype(np.float64)**2)):.1f} | Peak: {np.max(np.abs(mp4_data))}")

# 2. Segment by segment Energy breakdown (every 2 seconds)
print(f"\n{'Time Window':<15} | {'Call WAV (Asterisk MixMonitor)':<30} | {'MP4 Video (Local Room Audio)':<30}")
print(f"{'-'*15}-+-{'-'*30}-+-{'-'*30}")

max_dur = int(min(len(wav_data)/wav_sr, len(mp4_data)/mp4_sr))

for t in range(0, min(max_dur, 60), 2):
    t_start = t
    t_end = t + 2
    
    # WAV segment
    w_chunk = wav_data[t_start*wav_sr : t_end*wav_sr]
    w_rms = int(np.sqrt(np.mean(w_chunk.astype(np.float64)**2))) if len(w_chunk) > 0 else 0
    w_max = np.max(np.abs(w_chunk)) if len(w_chunk) > 0 else 0
    
    # MP4 segment
    m_chunk = mp4_data[t_start*mp4_sr : t_end*mp4_sr]
    m_rms = int(np.sqrt(np.mean(m_chunk.astype(np.float64)**2))) if len(m_chunk) > 0 else 0
    m_max = np.max(np.abs(m_chunk)) if len(m_chunk) > 0 else 0
    
    w_status = "SPEECH/AUDIO" if w_rms > 1000 else ("LOW/WHISPER" if w_rms > 400 else "SILENCE")
    m_status = "SPEECH/AUDIO" if m_rms > 1000 else ("LOW/WHISPER" if m_rms > 400 else "SILENCE")
    
    print(f"{t_start:02d}s - {t_end:02d}s      | RMS={w_rms:5d}, Peak={w_max:5d} [{w_status:<11}] | RMS={m_rms:5d}, Peak={m_max:5d} [{m_status:<11}]")
