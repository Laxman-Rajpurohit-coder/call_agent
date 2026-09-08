import os
import sys
import wave
import numpy as np

sys.stdout.reconfigure(encoding='utf-8')

pcap_wav = r"C:\daily_works\superfone_call\pcap_extracted_mic_rtp.wav"
mixmon_wav = r"C:\daily_works\superfone_call\recordings\f1351b1d-f57d-aef2-6e1e-38de6cbf65e1-20260820-043258.wav"

with wave.open(pcap_wav, 'rb') as wf:
    p_data = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16)
    p_sr = wf.getframerate()
    p_dur = len(p_data) / p_sr

with wave.open(mixmon_wav, 'rb') as wf:
    m_data = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16)
    m_sr = wf.getframerate()
    m_dur = len(m_data) / m_sr

print(f"=== Audio Synchronization Matrix ===")
print(f"RTP Payload Decoded (PCAP):  {p_dur:.2f}s | RMS: {np.sqrt(np.mean(p_data.astype(np.float64)**2)):.1f} | Peak: {np.max(np.abs(p_data))}")
print(f"Asterisk MixMonitor WAV:     {m_dur:.2f}s | RMS: {np.sqrt(np.mean(m_data.astype(np.float64)**2)):.1f} | Peak: {np.max(np.abs(m_data))}")

print(f"\n{'Time Window':<12} | {'RTP Payload RMS (Wire)':<24} | {'Asterisk MixMonitor RMS':<25} | {'AudioSocket & STT Result'}")
print(f"{'-'*12}-+-{'-'*24}-+-{'-'*25}-+-{'-'*35}")

min_d = int(min(p_dur, m_dur, 56))

for t in range(0, min_d, 4):
    p_chunk = p_data[t*p_sr : (t+4)*p_sr]
    p_rms = int(np.sqrt(np.mean(p_chunk.astype(np.float64)**2))) if len(p_chunk) > 0 else 0
    p_max = np.max(np.abs(p_chunk)) if len(p_chunk) > 0 else 0
    
    m_chunk = m_data[t*m_sr : (t+4)*m_sr]
    m_rms = int(np.sqrt(np.mean(m_chunk.astype(np.float64)**2))) if len(m_chunk) > 0 else 0
    m_max = np.max(np.abs(m_chunk)) if len(m_chunk) > 0 else 0
    
    stt_tag = "Speech Detected (energy > 1500)" if p_rms > 1200 else ("Soft Speech / Whisper" if p_rms > 300 else "Silence / Pause")
    
    print(f"{t:02d}s - {t+4:02d}s    | RMS={p_rms:5d}, Peak={p_max:5d}   | RMS={m_rms:5d}, Peak={m_max:5d}    | {stt_tag}")
