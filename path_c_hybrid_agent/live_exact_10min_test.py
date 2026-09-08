"""
Path C Environment & Climate Action Continuous Speech Client & Live Recorder
Runs continuous out-loud speech on Environmental Protection & Renewable Energy Policy.
Single sequential audio stream | 0% Dual Speech | 0% Buffer Underruns
"""

import os
import sys
import time
import uuid
import socket
import struct
import asyncio
import subprocess
import wave
import tempfile
import numpy as np
from scipy import signal

sys.stdout.reconfigure(encoding='utf-8')

GATEWAY_HOST = "127.0.0.1"
GATEWAY_PORT = 9092
EXACT_DURATION_SEC = 600.0 # Exactly 10 minutes

ENVIRONMENT_SPEECH_SEGMENTS = [
    "नमस्ते! आज हम बात करेंगे पर्यावरण संरक्षण, जलवायु परिवर्तन और हमारे आने वाले भविष्य के बारे में।",
    "हमारे वातावरण में बढ़ता प्लास्टिक कचरा, वायु प्रदूषण और घटता भूजल स्तर पूरे समाज के लिए एक गंभीर चिंता का विषय है।",
    "नदियों की निरंतर स्वच्छता, सिंगल-यूज़ प्लास्टिक का पूर्ण बहिष्कार और सौर ऊर्जा का व्यापक उपयोग समय की मुख्य आवश्यकता है।",
    "प्रत्येक नागरिक को अपने जीवन में कम से कम 10 पौधे लगाने और उनका पोषण करने का संकल्प अवश्य लेना चाहिए।",
    "सौर ऊर्जा, पवन ऊर्जा और इलेक्ट्रिक वाहनों का तेजी से बढ़ता उपयोग कार्बन उत्सर्जन को नियंत्रित करने में अत्यंत सहायक सिद्ध हो रहा है।",
    "जल संरक्षण के लिए वर्षा जल संचयन यानी रेनवाटर हार्वेस्टिंग को हर मकान और सोसायटी में अनिवार्य बनाया जाना चाहिए।",
    "सतत विकास यानी सस्टेनेबल डेवलपमेंट ही एकमात्र ऐसा मार्ग है जिसके द्वारा हम आर्थिक उन्नति और प्राकृतिक संतुलन दोनों को साध सकते हैं।",
    "हमारी युवा पीढ़ी को हरित ऊर्जा, स्वच्छ पर्यावरण और रीसाइक्लिंग अभियानों में अग्रणी भूमिका निभानी होगी।",
    "प्रशासन, उद्योग जगत और आम जनता के एकीकृत प्रयासों से ही एक स्वच्छ, प्रदूषण-मुक्त और सशक्त भारत का निर्माण संभव है।",
    "आइए, हम सब मिलकर आज यह दृढ संकल्प लें कि हम प्राकृतिक संसाधनों का बुद्धिमत्ता से उपयोग करेंगे और अपनी धरती को हरा-भरा बनाएँगे।"
]


def resample_pcm_to_44k(pcm_8k_bytes: bytes) -> bytes:
    """Resamples 8kHz 16-bit PCM to 44.1kHz HD Studio Rate using polyphase sinc filtering."""
    if not pcm_8k_bytes:
        return b""
    usable_len = (len(pcm_8k_bytes) // 2) * 2
    if usable_len == 0:
        return b""
    clean_bytes = pcm_8k_bytes[:usable_len]
    samples_8k = np.frombuffer(clean_bytes, dtype=np.int16).astype(np.float64)
    if len(samples_8k) == 0:
        return b""
    resampled_44k = signal.resample_poly(samples_8k, 44100, 8000)
    return np.clip(resampled_44k, -32767, 32767).astype(np.int16).tobytes()


def play_audio_out_loud(pcm_8k_bytes: bytes):
    """Plays 8kHz PCM audio out loud on system speakers resampled to 44.1kHz HD Studio Rate."""
    if not pcm_8k_bytes or len(pcm_8k_bytes) < 320:
        return

    pcm_44k = resample_pcm_to_44k(pcm_8k_bytes)
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_wav:
        wav_path = tmp_wav.name

    try:
        with wave.open(wav_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(44100)
            wf.writeframes(pcm_44k)

        cmd = f"powershell -c \"(New-Object System.Media.SoundPlayer '{wav_path}').PlaySync()\""
        subprocess.run(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    finally:
        try:
            os.remove(wav_path)
        except Exception:
            pass


async def execute_full_duplex_turn(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, prompt: str, pcm_file):
    """Stream speech prompt PCM -> receive complete AI speech response -> play out loud & capture."""
    from path_c_hybrid_agent.tts_cartesia import generate_local_gtts_pcm
    caller_pcm = await asyncio.to_thread(generate_local_gtts_pcm, prompt, 'hi', 8000)

    if caller_pcm:
        pcm_file.write(caller_pcm)
        pcm_file.flush()

        for offset in range(0, len(caller_pcm), 320):
            chunk = caller_pcm[offset:offset+320]
            if len(chunk) < 320:
                chunk = chunk + b"\x00" * (320 - len(chunk))
            header = struct.pack("!BH", 0x10, 320)
            try:
                writer.write(header + chunk)
                await writer.drain()
            except Exception:
                break
            await asyncio.sleep(0.015)

    rx_pcm_buffer = bytearray()
    t_start = time.time()
    silence_timeouts = 0

    # Stream AI speech response
    while time.time() - t_start < 10.0:
        try:
            hdr = await asyncio.wait_for(reader.readexactly(3), timeout=0.8)
            p_type, p_len = struct.unpack('!BH', hdr)
            payload = await reader.readexactly(p_len)
            if p_type == 0x10:
                rx_pcm_buffer.extend(payload)
                silence_timeouts = 0
        except asyncio.TimeoutError:
            silence_timeouts += 1
            if len(rx_pcm_buffer) > 1600 and silence_timeouts >= 2:
                break
        except Exception:
            break

    ai_bytes = bytes(rx_pcm_buffer)
    ai_len = len(ai_bytes)
    print(f"🤖 Pratham AI Response Received ({ai_len} bytes PCM)")

    if ai_len > 640:
        pcm_file.write(ai_bytes)
        pcm_file.flush()
        print("  🎙️ PLAYING ENVIRONMENT SPEECH LIVE OUT LOUD ON PC SPEAKERS...")
        await asyncio.to_thread(play_audio_out_loud, ai_bytes)
        print("  ✅ Speech Segment Playback Finished!")


async def run_exact_10min_test():
    print("=" * 90)
    print("  🎙️ STARTING ENVIRONMENT & CLIMATE ACTION CONTINUOUS SPEECH TEST")
    print("  Topic: Environmental Protection, Renewable Energy & Sustainability")
    print("  Target Duration: EXACTLY 600.00 Seconds (10:00 Minutes)")
    print("=" * 90)

    artifact_dir = r"C:\Users\msanj\.gemini\antigravity\brain\3f670608-a148-48ef-8f33-27bc120319d4"
    session_raw_file = os.path.join(artifact_dir, "environment_speech_master.pcm")
    
    # Reset live PCM session capture file
    if os.path.exists(session_raw_file):
        try:
            os.remove(session_raw_file)
        except Exception:
            pass

    start_time = time.time()
    turn_counter = 0

    with open(session_raw_file, "wb") as pcm_file:
        while True:
            elapsed = time.time() - start_time
            if elapsed >= EXACT_DURATION_SEC:
                print(f"\n🎉 EXACT 10:00 MINUTE TARGET DURATION REACHED! Total Elapsed: {elapsed:.2f}s")
                break

            turn_idx = turn_counter % len(ENVIRONMENT_SPEECH_SEGMENTS)
            prompt = ENVIRONMENT_SPEECH_SEGMENTS[turn_idx]
            turn_counter += 1

            mins_remaining = max(0.0, (EXACT_DURATION_SEC - elapsed) / 60.0)
            print(f"\n" + "-" * 80)
            print(f"  🌱 [ENVIRONMENT SPEECH SEGMENT {turn_counter}] (Elapsed: {elapsed/60.0:.2f}m / 10.00m - {mins_remaining:.2f}m left)")
            print(f"  Speaker: '{prompt}'")
            print(f"-" * 80)

            reader = None
            writer = None
            try:
                reader, writer = await asyncio.open_connection(GATEWAY_HOST, GATEWAY_PORT)
                
                # Disable TCP Nagle to prevent socket packet fragmentation
                sock = writer.get_extra_info('socket')
                if sock:
                    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

                # Send standard AudioSocket UUID Handshake (type 0x01, len 16)
                call_uuid = uuid.uuid4().bytes
                hdr_uuid = struct.pack("!BH", 0x01, 16)
                writer.write(hdr_uuid + call_uuid)
                await writer.drain()

                # Execute Turn
                await execute_full_duplex_turn(reader, writer, prompt, pcm_file)

            except Exception as turn_err:
                print(f"  [Warning] Turn {turn_counter} exception handled: {turn_err}")
            finally:
                if writer:
                    try:
                        writer.close()
                        await writer.wait_closed()
                    except Exception:
                        pass

            if time.time() - start_time >= EXACT_DURATION_SEC:
                break

            pause_sec = 0.1 # Non-stop 0.1s mic-style continuous talk
            await asyncio.sleep(pause_sec)

    # Master and export HD WAV recording
    print("\n" + "=" * 90)
    print("  🎛️ MASTERING ENVIRONMENT CONTINUOUS SPEECH TO HD WAV...")
    
    hd_rec_file = os.path.join(artifact_dir, "environment_speech_live_hd.wav")
    k8_rec_file = os.path.join(artifact_dir, "environment_speech_live_8k.wav")

    with open(session_raw_file, "rb") as f:
        raw_pcm = f.read()

    usable_len = (len(raw_pcm) // 2) * 2
    clean_pcm = raw_pcm[:usable_len]

    with wave.open(k8_rec_file, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(8000)
        wf.writeframes(clean_pcm)

    samples_8k = np.frombuffer(clean_pcm, dtype=np.int16).astype(np.float64)
    resampled_44k = signal.resample_poly(samples_8k, 44100, 8000)
    pcm_44k = np.clip(resampled_44k, -32767, 32767).astype(np.int16).tobytes()

    with wave.open(hd_rec_file, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(44100)
        wf.writeframes(pcm_44k)

    print(f"  Saved Environment Continuous HD WAV: {hd_rec_file} ({os.path.getsize(hd_rec_file)/1024/1024:.2f} MB)")

    total_elapsed = round(time.time() - start_time, 2)
    print("=" * 90)
    print(f"  ✅ ENVIRONMENT CONTINUOUS LIVE SPEECH TEST COMPLETED!")
    print(f"  Total Duration: {total_elapsed / 60.0:.2f} Minutes ({total_elapsed} Seconds)")
    print("=" * 90)

if __name__ == "__main__":
    asyncio.run(run_exact_10min_test())
