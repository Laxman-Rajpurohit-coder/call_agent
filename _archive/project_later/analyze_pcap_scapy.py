import os
import sys
import wave
import numpy as np
from scapy.all import rdpcap, UDP, IP
from faster_whisper import WhisperModel

sys.stdout.reconfigure(encoding='utf-8')

pcap_file = r"C:\daily_works\superfone_call\test700.pcap"
out_mic_wav = r"C:\daily_works\superfone_call\pcap_extracted_mic_rtp.wav"
out_bot_wav = r"C:\daily_works\superfone_call\pcap_extracted_bot_rtp.wav"

def ulaw2linear(ulaw_bytes):
    # Lookup table or standard formula for G.711 mu-law decoding
    import audioop
    return audioop.ulaw2lin(ulaw_bytes, 2)

print(f"Reading test700.pcap with Scapy...")
pkts = rdpcap(pcap_file)
print(f"Total packets read: {len(pkts)}")

# Filter UDP packets that contain RTP
streams = {}
for pkt in pkts:
    if IP in pkt and UDP in pkt:
        raw_payload = bytes(pkt[UDP].payload)
        # RTP header check: version 2 (first 2 bits == 2), length >= 12
        if len(raw_payload) >= 12:
            v_p_x_cc = raw_payload[0]
            version = (v_p_x_cc >> 6) & 0x03
            if version == 2:
                pt = raw_payload[1] & 0x7f
                seq = int.from_bytes(raw_payload[2:4], 'big')
                rtp_ts = int.from_bytes(raw_payload[4:8], 'big')
                ssrc = int.from_bytes(raw_payload[8:12], 'big')
                rtp_payload = raw_payload[12:]
                
                src_str = f"{pkt[IP].src}:{pkt[UDP].sport}"
                dst_str = f"{pkt[IP].dst}:{pkt[UDP].dport}"
                
                if ssrc not in streams:
                    streams[ssrc] = {
                        "src": src_str,
                        "dst": dst_str,
                        "pt": pt,
                        "packets": []
                    }
                streams[ssrc]["packets"].append({
                    "seq": seq,
                    "ts": rtp_ts,
                    "payload": rtp_payload
                })

print(f"\nDiscovered {len(streams)} RTP Stream(s) in PCAP:")
for ssrc, sinfo in streams.items():
    pk_list = sinfo["packets"]
    tot_bytes = sum(len(p["payload"]) for p in pk_list)
    dur_sec = len(pk_list) * 0.02
    print(f"  Stream SSRC 0x{ssrc:08x}: {len(pk_list)} packets (~{dur_sec:.2f}s) | {sinfo['src']} -> {sinfo['dst']} | PT={sinfo['pt']} | Payload: {tot_bytes} B")

model = WhisperModel("tiny", device="cpu", compute_type="int8", cpu_threads=4)

for idx, (ssrc, sinfo) in enumerate(streams.items()):
    pk_list = sorted(sinfo["packets"], key=lambda x: x["seq"])
    raw_ulaw = b"".join(p["payload"] for p in pk_list)
    pcm16 = ulaw2linear(raw_ulaw)
    
    samples = np.frombuffer(pcm16, dtype=np.int16)
    sr = 8000
    dur = len(samples) / sr
    rms = np.sqrt(np.mean(samples.astype(np.float64)**2))
    peak = np.max(np.abs(samples))
    
    out_wav = out_mic_wav if idx == 0 else out_bot_wav
    with wave.open(out_wav, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm16)
        
    print(f"\n=======================================================")
    print(f"STREAM {idx+1} (SSRC 0x{ssrc:08x}, {sinfo['src']} -> {sinfo['dst']}):")
    print(f"  Duration: {dur:.2f}s | Sample Rate: 8000Hz | Total Packets: {len(pk_list)}")
    print(f"  Average RMS Energy: {rms:.1f} | Peak Amplitude: {peak} (Max scale: 32767)")
    print(f"  Decoded WAV saved to: {out_wav}")
    print(f"-------------------------------------------------------")
    print("Second-by-second Energy Profile directly from inside RTP packets:")
    for t in range(0, int(dur), 2):
        chunk = samples[t*sr : (t+2)*sr]
        c_rms = int(np.sqrt(np.mean(chunk.astype(np.float64)**2))) if len(chunk) > 0 else 0
        c_max = np.max(np.abs(chunk)) if len(chunk) > 0 else 0
        tag = "LOUD SPEECH" if c_rms > 1500 else ("NORMAL SPEECH" if c_rms > 500 else ("LOW/WHISPER" if c_rms > 200 else "SILENCE"))
        print(f"  {t:02d}s - {t+2:02d}s: RMS={c_rms:5d} | Peak={c_max:5d} | [{tag}]")
        
    float_data = samples.astype(np.float32) / 32768.0
    segments, _ = model.transcribe(float_data, beam_size=1, vad_filter=True)
    print("\nWhisper Transcription directly from raw RTP payload data:")
    for s in segments:
        print(f"  [{s.start:5.1f}s -> {s.end:5.1f}s] {s.text}")

print(f"\nPCAP decoding and analysis finished successfully.")
