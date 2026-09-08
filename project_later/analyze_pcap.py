import os
import sys
import struct
import audioop
import wave
import numpy as np
from faster_whisper import WhisperModel

sys.stdout.reconfigure(encoding='utf-8')

pcap_file = r"C:\daily_works\superfone_call\test700.pcap"
out_mic_wav = r"C:\daily_works\superfone_call\pcap_extracted_mic_rtp.wav"
out_bot_wav = r"C:\daily_works\superfone_call\pcap_extracted_bot_rtp.wav"

def parse_pcap(filepath):
    """Parse raw PCAP and extract RTP packets based on payload type and UDP ports."""
    with open(filepath, 'rb') as f:
        # PCAP Global Header: 24 bytes
        global_header = f.read(24)
        if len(global_header) < 24:
            print("Invalid PCAP file.")
            return []
        
        magic_number = struct.unpack('<I', global_header[:4])[0]
        if magic_number == 0xa1b2c3d4:
            endian = '<'
        elif magic_number == 0xd4c3b2a1:
            endian = '>'
        else: # nanosecond or other variant
            endian = '<'

        packets = []
        while True:
            pkt_hdr = f.read(16)
            if len(pkt_hdr) < 16:
                break
            ts_sec, ts_usec, incl_len, orig_len = struct.unpack(f'{endian}IIII', pkt_hdr)
            pkt_data = f.read(incl_len)
            if len(pkt_data) < incl_len:
                break
            
            # SLL (Linux cooked) is 16 bytes, Ethernet is 14 bytes
            # Check IP header
            ip_offset = None
            if pkt_data[:2] == b'\x00\x00' or pkt_data[:2] == b'\x00\x04': # SLL
                ip_offset = 16
            else: # Standard Ethernet / loopback
                ip_offset = 14

            if len(pkt_data) <= ip_offset:
                continue

            ip_ver = (pkt_data[ip_offset] >> 4) & 0x0f
            if ip_ver != 4:
                continue
            
            ip_header_len = (pkt_data[ip_offset] & 0x0f) * 4
            protocol = pkt_data[ip_offset + 9]
            if protocol != 17: # UDP
                continue
            
            src_ip = ".".join(str(b) for b in pkt_data[ip_offset+12:ip_offset+16])
            dst_ip = ".".join(str(b) for b in pkt_data[ip_offset+16:ip_offset+20])

            udp_offset = ip_offset + ip_header_len
            if len(pkt_data) < udp_offset + 8:
                continue
            
            src_port, dst_port, udp_len = struct.unpack('!HHH', pkt_data[udp_offset:udp_offset+6])
            udp_payload = pkt_data[udp_offset+8 : udp_offset+udp_len]

            # RTP packet format: at least 12 bytes
            if len(udp_payload) >= 12:
                v_p_x_cc = udp_payload[0]
                version = (v_p_x_cc >> 6) & 0x03
                if version == 2: # RTP version 2
                    pt = udp_payload[1] & 0x7f
                    seq = struct.unpack('!H', udp_payload[2:4])[0]
                    rtp_ts = struct.unpack('!I', udp_payload[4:8])[0]
                    ssrc = struct.unpack('!I', udp_payload[8:12])[0]
                    rtp_payload = udp_payload[12:]
                    
                    packets.append({
                        "ts": ts_sec + ts_usec / 1e6,
                        "src_ip": src_ip,
                        "dst_ip": dst_ip,
                        "src_port": src_port,
                        "dst_port": dst_port,
                        "pt": pt,
                        "seq": seq,
                        "rtp_ts": rtp_ts,
                        "ssrc": ssrc,
                        "payload": rtp_payload
                    })
    return packets

print(f"Parsing test700.pcap...")
pkts = parse_pcap(pcap_file)
print(f"Total RTP packets extracted: {len(pkts)}")

# Separate into streams by SSRC
streams = {}
for p in pkts:
    ssrc = p["ssrc"]
    if ssrc not in streams:
        streams[ssrc] = []
    streams[ssrc].append(p)

print(f"\nDiscovered {len(streams)} RTP Stream(s):")
for ssrc, s_pkts in streams.items():
    p0 = s_pkts[0]
    total_bytes = sum(len(p["payload"]) for p in s_pkts)
    dur_sec = len(s_pkts) * 0.02
    print(f"  Stream SSRC 0x{ssrc:08x}: {len(s_pkts)} packets (~{dur_sec:.2f}s) | {p0['src_ip']}:{p0['src_port']} -> {p0['dst_ip']}:{p0['dst_port']} | PT={p0['pt']} ({'PCMU' if p0['pt']==0 else 'other'}) | Payload: {total_bytes} B")

# Decode PCMU (G.711 mu-law) to Linear PCM16 for each stream
model = WhisperModel("tiny", device="cpu", compute_type="int8", cpu_threads=4)

for idx, (ssrc, s_pkts) in enumerate(streams.items()):
    # Sort packets by sequence number handling wrap-around
    s_pkts = sorted(s_pkts, key=lambda x: x["seq"])
    
    # Concatenate payloads
    raw_ulaw = b"".join(p["payload"] for p in s_pkts)
    # audioop.ulaw2lin converts 8-bit mu-law to 16-bit linear PCM (2 bytes per sample)
    pcm16 = audioop.ulaw2lin(raw_ulaw, 2)
    
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
    
    p0 = s_pkts[0]
    print(f"\n=======================================================")
    print(f"STREAM {idx+1} (SSRC 0x{ssrc:08x}, {p0['src_ip']} -> {p0['dst_ip']}):")
    print(f"  Duration: {dur:.2f}s | Sample Rate: 8000Hz")
    print(f"  Average RMS Energy: {rms:.1f} | Peak Amplitude: {peak} (Max scale: 32767)")
    print(f"  Decoded WAV saved to: {out_wav}")
    print(f"-------------------------------------------------------")
    print("Second-by-second Energy Profile directly from RTP packets:")
    for t in range(0, int(dur), 2):
        chunk = samples[t*sr : (t+2)*sr]
        c_rms = int(np.sqrt(np.mean(chunk.astype(np.float64)**2))) if len(chunk) > 0 else 0
        c_max = np.max(np.abs(chunk)) if len(chunk) > 0 else 0
        tag = "LOUD SPEECH" if c_rms > 1500 else ("NORMAL SPEECH" if c_rms > 500 else ("LOW/WHISPER" if c_rms > 200 else "SILENCE"))
        print(f"  {t:02d}s - {t+2:02d}s: RMS={c_rms:5d} | Peak={c_max:5d} | [{tag}]")
    
    # Transcribe directly from raw RTP payload
    float_data = samples.astype(np.float32) / 32768.0
    segments, _ = model.transcribe(float_data, beam_size=1, vad_filter=True)
    print("\nWhisper Transcription directly from RTP packets:")
    for s in segments:
        print(f"  [{s.start:5.1f}s -> {s.end:5.1f}s] {s.text}")

print("\nPCAP analysis complete.")
