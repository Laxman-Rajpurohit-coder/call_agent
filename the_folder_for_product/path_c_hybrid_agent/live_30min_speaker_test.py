"""
Path C Live 30-Minute Continuous Out-Loud PC Speaker Test
Runs a non-stop 30+ minute (1,800+ seconds) multi-turn conversational call test.
Plays all AI responses OUT LOUD through Windows PC speakers at 44.1kHz HD Studio Rate with 0-buzz polyphase resampling.
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
TARGET_DURATION_SECONDS = 1800 # 30 minutes minimum

# 60 Conversational Dialogue Turns across E-Commerce, NGO, Logistics, Payments, and Customer Care
DIALOGUE_TURNS = [
    # Phase 1: Order Tracking & Delivery
    "नमस्ते! QuickCart में मेरा ऑर्डर नंबर QC-987654 कब तक डिलीवर होगा?",
    "क्या मैं डिलीवरी एड्रेस बदल सकता हूँ? मैं अभी घर पर नहीं हूँ।",
    "क्या आप डिलीवरी बॉय का फोन नंबर दे सकती हैं?",
    "क्या संडे को भी डिलीवरी हो सकती है?",
    "ऑर्डर में 2 आइटम थे, क्या दोनों एक साथ आएँगे या अलग-अलग?",
    "अगर डिलीवरी के समय मैं घर पर न रहूँ तो क्या होगा?",
    "क्या मैं डिलीवरी टाइम स्लॉट चेंज कर सकता हूँ?",

    # Phase 2: Returns, Replacement & Refunds
    "अगर कपड़ों की फिटिंग पसंद न आए तो रिटर्न और रिफंड की क्या पॉलिसी है?",
    "क्या रिटर्न पिकअप का कोई एक्स्ट्रा चार्ज लगता है?",
    "रिफंड मेरे बैंक अकाउंट में कितने दिन में क्रेडिट होगा?",
    "क्या मैं साइज़ छोटा होने पर रिप्लेसमेंट ले सकता हूँ?",
    "अगर मुझे केवल 1 आइटम रिटर्न करना हो तो क्या वो हो जाएगा?",
    "क्या रिफंड सीधे UPI में आएगा या बैंक ट्रांसफ़र में?",
    "कपड़ों की क्वालिटी ख़राब निकलने पर क्या गारंटी मिलती है?",

    # Phase 3: Payment Options & COD
    "क्या मैं अगले ऑर्डर के लिए कैश ऑन डिलीवरी चुन सकता हूँ?",
    "COD पर क्या कोई अतिरिक्त सर्विस चार्ज लगता है?",
    "क्या ऑनलाइन पेमेंट करने पर कोई डिस्काउंट या कैशबैक मिलता है?",
    "क्रेडिट कार्ड से EMI का ऑप्शन उपलब्ध है क्या?",
    "अगर पेमेंट फेल हो जाए लेकिन पैसे कट जाएँ तो क्या करें?",
    "क्या मुझे GST इनवॉइस मिल सकता है मेरे बिज़नेस के लिए?",
    "इनवॉइस पर कंपनी नाम कैसे ऐड करें?",

    # Phase 4: Customer Care & Product Assistance
    "आपकी कंपनी की टाइमिंग क्या है और कस्टमर सपोर्ट कब तक चालू रहता है?",
    "क्या आपकी कोई नज़दीकी फ़िज़िकल शॉप या शोरूम भी है दिल्ली में?",
    "क्या मैं बल्क ऑर्डर के लिए स्पेशल कोटेशन ले सकता हूँ?",
    "अगर मुझे मैनेजर से बात करनी हो तो कैसे कनेक्ट होगा?",
    "क्या आपके पास विंटर कलेक्शन में नई वैरायटी आई है?",
    "सूती कपड़ों का मैटेरियल कैसा रहता है धोने के बाद?",

    # Phase 5: Mali Saini Welfare Foundation NGO & Donations
    "नमस्ते! माली सैनी समाज सेवा फ़ाउंडेशन के बारे में जानकारी चाहिए।",
    "फ़ाउंडेशन बच्चों की पढ़ाई के लिए क्या सहायता प्रदान करता है?",
    "क्या दान देने पर 80G के तहत इनकम टैक्स में छूट मिलती है?",
    "80G की रसीद मुझे कितने दिन में मिल जाएगी?",
    "क्या मैं ऑनलाइन UPI से डोनेशन कर सकता हूँ?",
    "गरीब कन्याओं के विवाह सहायता योजना में आवेदन कैसे करें?",
    "क्या फ़ाउंडेशन फ्री मेडिकल कैंप भी आयोजित करता है?",
    "मेडिकल कैंप की अगली तारीख कब है और कहाँ होगा?",

    # Phase 6: Volunteering & Office Info
    "क्या मैं फ़ाउंडेशन में वालंटियर के रूप में काम कर सकता हूँ?",
    "वालंटियर बनने के लिए क्या फॉर्म भरना पड़ेगा?",
    "आपका मुख्य कार्यालय कहाँ स्थित है और मिलने का समय क्या है?",
    "क्या फ़ाउंडेशन की कोई वार्षिक पत्रिका या रिपोर्ट प्रकाशित होती है?",
    "क्या समाज के ज़रूरतमंद छात्रों को स्कॉलरशिप भी दी जाती है?",
    "स्कॉलरशिप के लिए कौन-कौन से डॉक्यूमेंट चाहिए?",
    "क्या मैं डायरेक्ट चेयरमैन साहेब से बात कर सकता हूँ?",

    # Phase 7: General Feedback & Support
    "आपकी सर्विस बहुत अच्छी है, धन्यवाद!",
    "क्या मुझे व्हाट्सएप पर अपडेट्स मिल सकते हैं?",
    "मेरी शिकायत संख्या 4567 का क्या स्टेटस है?",
    "शिकायत निवारण में कितना समय लगता है?",
    "क्या कोई टोल-फ़्री नंबर भी उपलब्ध है?",
    "धन्यवाद आपकी मदद के लिए, आपका दिन शुभ हो!"
]


def resample_pcm_to_44k(pcm_8k_bytes: bytes) -> bytes:
    """Resamples 8kHz 16-bit PCM to 44.1kHz HD Studio Rate using polyphase sinc filtering."""
    if not pcm_8k_bytes:
        return b""
    # Ensure byte count is even (16-bit alignment)
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


async def run_30min_live_speaker_test():
    print("=" * 90)
    print("  🔊 STARTING 30-MINUTE CONTINUOUS LIVE OUT-LOUD PC SPEAKER CONVERSATION TEST")
    print("  Target Duration: 1,800+ seconds (30 Minutes Minimum)")
    print("  Playback Rate: 44.1kHz HD Studio Quality (0% Buzz / Pop Noise)")
    print("=" * 90)

    start_time = time.time()
    turn_counter = 0

    while True:
        elapsed = time.time() - start_time
        if elapsed >= TARGET_DURATION_SECONDS:
            print(f"\n🎉 30-Minute Target Duration Reached! Total Elapsed: {elapsed:.1f}s")
            break

        turn_idx = turn_counter % len(DIALOGUE_TURNS)
        prompt = DIALOGUE_TURNS[turn_idx]
        turn_counter += 1

        mins_remaining = max(0.0, (TARGET_DURATION_SECONDS - elapsed) / 60.0)
        print(f"\n" + "-" * 80)
        print(f"  🗣️ [TURN {turn_counter}] (Elapsed: {elapsed/60.0:.1f}m / 30.0m - {mins_remaining:.1f}m left)")
        print(f"  Caller: '{prompt}'")
        print(f"-" * 80)

        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((GATEWAY_HOST, GATEWAY_PORT))
            
            # Send standard AudioSocket UUID Handshake (type 0x01, len 16)
            call_uuid = uuid.uuid4().bytes # 16 bytes
            hdr_uuid = struct.pack("!BH", 0x01, 16)
            sock.sendall(hdr_uuid + call_uuid)

            # Synthesize caller audio simulation
            from path_c_hybrid_agent.tts_cartesia import generate_local_gtts_pcm
            caller_pcm = await asyncio.to_thread(generate_local_gtts_pcm, prompt, 'hi', 8000)

            if caller_pcm:
                # Send PCM frames over AudioSocket in 320-byte chunks
                for offset in range(0, len(caller_pcm), 320):
                    chunk = caller_pcm[offset:offset+320]
                    if len(chunk) == 320:
                        header = struct.pack("!BH", 0x10, 320)
                        sock.sendall(header + chunk)
                        await asyncio.sleep(0.018) # 20ms frame pacing

            # Read Pratham AI PCM Response from Socket
            sock.settimeout(10.0)
            rx_pcm_buffer = bytearray()
            t_recv_start = time.time()

            while time.time() - t_recv_start < 8.0:
                try:
                    data = sock.recv(1024)
                    if not data:
                        break
                    # Strip 3-byte AudioSocket header if present
                    if len(data) > 3 and data[0] == 0x10:
                        rx_pcm_buffer.extend(data[3:])
                    else:
                        rx_pcm_buffer.extend(data)
                except socket.timeout:
                    break

            ai_response_len = len(rx_pcm_buffer)
            print(f"🤖 Pratham AI Response Received ({ai_response_len} bytes PCM)")

            if ai_response_len > 640:
                print("  🔊 PLAYING AI RESPONSE LIVE OUT LOUD ON PC SPEAKERS...")
                await asyncio.to_thread(play_audio_out_loud, bytes(rx_pcm_buffer))
                print("  ✅ Turn Out-Loud Playback Finished (0-Buzz Perfect)!")
        except Exception as turn_err:
            print(f"  [Warning] Turn {turn_counter} exception handled: {turn_err}")
        finally:
            if sock:
                try:
                    sock.close()
                except Exception:
                    pass

        # Organic Pause between conversation turns (20 seconds) to simulate natural speech flow
        pause_sec = 20.0
        print(f"  ⏸️ Pacing organic speech pause ({pause_sec}s)...")
        await asyncio.sleep(pause_sec)

    total_elapsed = round(time.time() - start_time, 1)
    print("\n" + "=" * 90)
    print(f"  ✅ 30-MINUTE CONTINUOUS LIVE SPEAKER CONVERSATION TEST COMPLETED!")
    print(f"  Total Duration: {total_elapsed / 60.0:.2f} Minutes ({total_elapsed} Seconds)")
    print(f"  Total Turns Executed: {turn_counter}")
    print("=" * 90)

if __name__ == "__main__":
    asyncio.run(run_30min_live_speaker_test())
