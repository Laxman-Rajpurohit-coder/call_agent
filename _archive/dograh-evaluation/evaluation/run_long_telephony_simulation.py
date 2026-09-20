"""
run_long_telephony_simulation.py  —  VOICE → VOICE → VOICE  (Live Playback)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
You can HEAR the full conversation live as it happens:
  ► Caller voice  (Piper TTS)  plays through your speakers BEFORE being sent
  ► Bot voice arrives over AudioSocket and plays through speakers IMMEDIATELY
  ► Bot audio is then transcribed back to text (Leg 3: STT :9094)

Full loop per turn:
  1. Customer text → Piper TTS → 8 kHz PCM → play on speakers → stream to gateway
  2. Gateway: STT→LLM→TTS → streams bot audio back over AudioSocket
  3. Bot audio arrives → play on speakers live → transcribe via STT :9094
"""
import os
import sys
import json
import time
import struct
import wave
import asyncio
import uuid
import threading
import numpy as np
import httpx
from scipy.signal import resample_poly
from faster_whisper import WhisperModel

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.abspath("."))
sys.path.insert(0, os.path.abspath("dograh-evaluation/tools"))

# Lazy-loaded multilingual Whisper model for Leg 3 bot transcription
_leg3_whisper: WhisperModel = None

def _get_leg3_whisper() -> WhisperModel:
    global _leg3_whisper
    if _leg3_whisper is None:
        print("  [Leg 3] Loading faster-whisper 'base' multilingual for bot transcription...")
        _leg3_whisper = WhisperModel("base", device="cpu", compute_type="int8", cpu_threads=4)
        print("  [Leg 3] Whisper ready.")
    return _leg3_whisper

# ── Service addresses ─────────────────────────────────────────────────────────
GATEWAY_HOST = "127.0.0.1"
GATEWAY_PORT = 9092
STT_URL      = "http://127.0.0.1:9094/stt"

# ── Output artifact directory ─────────────────────────────────────────────────
ART_DIR = r"C:\Users\msanj\.gemini\antigravity\brain\3f670608-a148-48ef-8f33-27bc120319d4"

# ── Piper model paths ─────────────────────────────────────────────────────────
PIPER_EXE = r"c:\daily_works\superfone_call\piper\piper\piper.exe"
MODEL_EN  = r"c:\daily_works\superfone_call\models\en_US-lessac-medium.onnx"
MODEL_HI  = r"c:\daily_works\superfone_call\models\hi_IN-pratham-medium.onnx"

# ── Speaker sample rate (sounddevice will resample if needed) ─────────────────
SPEAKER_RATE = 22050   # Piper native rate for caller playback
BOT_RATE     = 8000    # Gateway streams 8 kHz for bot playback

# ── 8 open-topic natural human conversation scenarios ─────────────────────────
CUSTOMER_PERSONAS = [
    {
        "id": "EP-01",
        "title": "Weekend Plans & Movie Recommendations (EN)",
        "turns": [
            {"lang": "en", "text": "Hey, what are some good science fiction or thriller movies you would recommend for the weekend?"},
            {"lang": "en", "text": "I really loved movies like Interstellar and Inception. What makes space movies so captivating?"},
            {"lang": "en", "text": "What do you usually like to do when relaxing on a quiet Sunday afternoon?"},
            {"lang": "en", "text": "That sounds wonderful. Thanks for the great recommendations!"},
        ],
    },
    {
        "id": "EP-02",
        "title": "मौसम और चाय की चर्चा (Hindi Daily Small Talk & Weather)",
        "turns": [
            {"lang": "hi", "text": "नमस्ते! आज मौसम कैसा लग रहा है? क्या आपके यहाँ हल्की ठंडी हवा चल रही है?"},
            {"lang": "hi", "text": "ऐसे सुहावने मौसम में गरमा-गरम अदरक वाली चाय पीने का मज़ा ही अलग है, आपका क्या ख्याल है?"},
            {"lang": "hi", "text": "आपकी पसंदीदा चाय बनाने का कोई खास तरीका या नुस्खा है क्या?"},
            {"lang": "hi", "text": "बहुत खूब, आपसे बातचीत करके बहुत अच्छा लगा। धन्यवाद!"},
        ],
    },
    {
        "id": "EP-03",
        "title": "Travel, Trekking & Mountain Destinations (EN)",
        "turns": [
            {"lang": "en", "text": "Hello! I am planning a holiday trip to the Himalayas in Himachal. Where should I visit?"},
            {"lang": "en", "text": "Is Manali or Dharamshala better if I want peaceful mountain views and cozy cafes?"},
            {"lang": "en", "text": "What are three essential things I should definitely pack for a mountain trek?"},
            {"lang": "en", "text": "Awesome advice, I really appreciate your suggestions."},
        ],
    },
    {
        "id": "EP-04",
        "title": "भारतीय भोजन और पसंदीदा व्यंजन (Hindi Food & Cooking Chat)",
        "turns": [
            {"lang": "hi", "text": "नमस्ते, मुझे आज रात के खाने के लिए कुछ स्वादिष्ट और हल्का बनाने का मन है। क्या सुझाव देंगे?"},
            {"lang": "hi", "text": "पनीर भुर्जी या दाल खिचड़ी में से क्या जल्दी और बढ़िया बन जाएगा?"},
            {"lang": "hi", "text": "दाल खिचड़ी के साथ थोड़ा सा देसी घी और आम का अचार हो तो क्या बात है!"},
            {"lang": "hi", "text": "आपने तो मुंह में पानी ला दिया! बहुत-बहुत शुक्रिया।"},
        ],
    },
    {
        "id": "EP-05",
        "title": "Artificial Intelligence & Future Technology (EN)",
        "turns": [
            {"lang": "en", "text": "Hi! How do you think AI and voice technology will change the way we live over the next few years?"},
            {"lang": "en", "text": "Do you think AI will help students and professionals learn new languages much faster?"},
            {"lang": "en", "text": "What is one recent technological innovation that you find truly fascinating?"},
            {"lang": "en", "text": "Fascinating perspective! Thanks for sharing your thoughts."},
        ],
    },
    {
        "id": "EP-06",
        "title": "क्रिकेट और खेलकूद पर बातचीत (Hindi Sports & Cricket Chat)",
        "turns": [
            {"lang": "hi", "text": "नमस्ते! क्या आप भारतीय क्रिकेट टीम के रोमांचक मैचों को फॉलो करते हैं?"},
            {"lang": "hi", "text": "आपके हिसाब से टी-20 क्रिकेट में सबसे रोमांचक बात क्या होती है?"},
            {"lang": "hi", "text": "विराट कोहली और रोहित शर्मा की बल्लेबाज़ी में आपको क्या सबसे खास लगता है?"},
            {"lang": "hi", "text": "बिल्कुल सही कहा आपने, मज़ा आ गया क्रिकेट पर बात करके।"},
        ],
    },
    {
        "id": "EP-07",
        "title": "Books, Reading Habits & Personal Growth (EN)",
        "turns": [
            {"lang": "en", "text": "Hello, I want to build a consistent daily book reading habit. Any practical tips?"},
            {"lang": "en", "text": "Have you heard of Atomic Habits by James Clear? What is the main idea behind small habits?"},
            {"lang": "en", "text": "How many pages or minutes a day do you think is a realistic starting goal for a beginner?"},
            {"lang": "en", "text": "That is really encouraging and practical advice. Thank you!"},
        ],
    },
    {
        "id": "EP-08",
        "title": "सुबह की सैर और फिटनेस (Hindi Health, Fitness & Routine)",
        "turns": [
            {"lang": "hi", "text": "नमस्ते! सुबह जल्दी उठकर ताज़ी हवा में सैर करने के क्या फायदे हैं?"},
            {"lang": "hi", "text": "क्या हर दिन 20 से 30 मिनट योग या प्राणायाम करने से मानसिक तनाव कम होता है?"},
            {"lang": "hi", "text": "एक स्वस्थ और ऊर्जावान दिनचर्या के लिए अच्छी नींद कितनी ज़रूरी है?"},
            {"lang": "hi", "text": "बहुत ही उपयोगी और प्रेरणादायक बातें बताईं आपने। धन्यवाद!"},
        ],
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# AUDIO PLAYBACK  (runs in a background thread, non-blocking for asyncio)
# ─────────────────────────────────────────────────────────────────────────────
def _play_pcm(pcm_bytes: bytes, sample_rate: int, label: str):
    """Play raw s16le PCM through Windows system speakers using winsound."""
    import tempfile
    import winsound
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
            tmp_path = tf.name
            with wave.open(tf, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sample_rate)
                wf.writeframes(pcm_bytes)
        winsound.PlaySound(tmp_path, winsound.SND_FILENAME)
        try:
            os.remove(tmp_path)
        except Exception:
            pass
    except Exception as ex:
        try:
            import sounddevice as sd
            samples = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
            sd.play(samples, samplerate=sample_rate, blocking=True)
        except Exception as sd_ex:
            print(f"   [⚠️  Speaker playback skipped — {ex} / {sd_ex}]")


def play_async(pcm_bytes: bytes, sample_rate: int, label: str):
    """Non-blocking speaker playback — fires in a daemon thread."""
    t = threading.Thread(target=_play_pcm, args=(pcm_bytes, sample_rate, label), daemon=True)
    t.start()
    return t


# ─────────────────────────────────────────────────────────────────────────────
# LEG 1 — Customer text → Piper TTS → raw PCM  (22 kHz native + 8 kHz copy)
# ─────────────────────────────────────────────────────────────────────────────
def synthesize_caller_voice(text: str, lang: str = "en"):
    """Returns (pcm_22k_bytes, pcm_8k_bytes): 22 kHz for speakers, 8 kHz for gateway."""
    import subprocess
    model_onnx = MODEL_HI if lang == "hi" else MODEL_EN
    cmd = [PIPER_EXE, "--model", model_onnx, "--output-raw"]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    raw_22k, _ = proc.communicate(input=text.encode("utf-8"))
    if not raw_22k:
        silence_22k = b"\x00\x00" * 22050
        silence_8k  = b"\x00\x00" * 8000
        return silence_22k, silence_8k

    samples_22k = np.frombuffer(raw_22k, dtype=np.int16)
    samples_8k  = resample_poly(samples_22k, 160, 441).astype(np.int16)
    return raw_22k, samples_8k.tobytes()


# ─────────────────────────────────────────────────────────────────────────────
# LEG 3 — Bot audio → STT :9094 → text transcript
# ─────────────────────────────────────────────────────────────────────────────
async def transcribe_bot_audio(bot_pcm_8k: bytes, label: str = "", lang: str = None) -> str:
    """
    Leg 3: Upsample 8kHz → 16kHz, save WAV, transcribe with multilingual Whisper.
    Runs in executor thread so it doesn't block asyncio.
    """
    if len(bot_pcm_8k) < 1600:
        return ""

    # Save WAV for human listening review
    if label:
        wav_path = os.path.join(ART_DIR, f"bot_reply_{label}.wav")
        try:
            with wave.open(wav_path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(8000)
                wf.writeframes(bot_pcm_8k)
        except Exception:
            pass

    def _do_transcribe():
        try:
            model = _get_leg3_whisper()
            # Upsample 8kHz → 16kHz for Whisper
            samples_8k  = np.frombuffer(bot_pcm_8k, dtype=np.int16).astype(np.float32) / 32768.0
            samples_16k = resample_poly(samples_8k, 2, 1)
            whisper_lang = lang if lang in ("en", "hi") else None
            segments, _ = model.transcribe(
                samples_16k,
                beam_size=3,
                language=whisper_lang,
                condition_on_previous_text=False,
                vad_filter=True,
                vad_parameters={"min_silence_duration_ms": 300},
            )
            return " ".join(s.text.strip() for s in segments).strip()
        except Exception as ex:
            return f"[STT error: {ex}]"

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _do_transcribe)




def _flush_telemetry(all_telemetry: list):
    path = os.path.join(ART_DIR, "simulation_telemetry.json")
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(all_telemetry, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# EPISODE RUNNER
# ─────────────────────────────────────────────────────────────────────────────
async def run_episode(
    persona: dict,
    episode_idx: int,
    total_episodes: int,
    all_telemetry: list,
    master_audio_frames: list,
):
    call_uuid = uuid.uuid4()
    print()
    print("█" * 80)
    print(f"  EPISODE {episode_idx}/{total_episodes}: {persona['title']}")
    print(f"  UUID: {call_uuid}")
    print("█" * 80)

    # Open AudioSocket TCP connection
    try:
        reader, writer = await asyncio.open_connection(GATEWAY_HOST, GATEWAY_PORT)
    except Exception as ex:
        print(f"  ✗ Cannot connect to gateway: {ex}")
        return

    # Send AudioSocket UUID handshake (type 0x01)
    writer.write(struct.pack("!BH", 0x01, 16) + call_uuid.bytes)
    # Send initial 20ms audio frame (type 0x10) to notify gateway the call is active
    writer.write(struct.pack("!BH", 0x10, 320) + (b"\x00" * 320))
    await writer.drain()

    rx_queue: asyncio.Queue[bytes] = asyncio.Queue()
    session_alive = True

    async def _receiver():
        while session_alive:
            try:
                hdr = await reader.readexactly(3)
                p_type, p_len = struct.unpack("!BH", hdr)
                payload = await reader.readexactly(p_len) if p_len else b""
                if p_type == 0x10 and payload:
                    await rx_queue.put(payload)
                elif p_type == 0x00:
                    break
            except Exception:
                break

    receiver_task = asyncio.create_task(_receiver())

    # ── Wait for bot welcome greeting ─────────────────────────────────────────
    print("\n🔔 Waiting for bot greeting...")
    greeting_bytes = bytearray()
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < 6.0:
        try:
            chunk = await asyncio.wait_for(rx_queue.get(), timeout=0.35)
            greeting_bytes.extend(chunk)
            master_audio_frames.append(chunk)
        except (asyncio.TimeoutError, TimeoutError):
            if len(greeting_bytes) > 4000:
                break

    greet_dur_s = len(greeting_bytes) / 16000.0
    print(f"🤖 [BOT GREETING — {greet_dur_s:.1f}s] ► Playing through speakers...")
    play_t = play_async(bytes(greeting_bytes), BOT_RATE, "greeting")
    play_t.join()

    greet_text = await transcribe_bot_audio(bytes(greeting_bytes), label=f"{persona['id']}_greeting", lang="en")
    print(f'   📝 "{greet_text or "(no transcript)"}"')

    # ── Turn-by-turn ──────────────────────────────────────────────────────────
    for turn_idx, turn in enumerate(persona["turns"], 1):
        lang  = turn["lang"]
        text  = turn["text"]
        print()
        print(f"  ┌─ Turn {turn_idx}/{len(persona['turns'])}  [{lang.upper()}] {'─'*50}")
        print(f"  │ 👤 CUSTOMER: \"{text}\"")

        # ── LEG 1: Synthesize caller voice ────────────────────────────────────
        t_synth = time.perf_counter()
        pcm_22k, pcm_8k = synthesize_caller_voice(text, lang)
        synth_ms    = (time.perf_counter() - t_synth) * 1000.0
        caller_dur  = len(pcm_8k) / 16000.0
        print(f"  │ 🎙️  LEG 1 — Piper TTS: {caller_dur:.2f}s audio ({synth_ms:.0f}ms)")

        # Play caller voice through speakers (so you can hear it)
        print(f"  │ 🔈 Playing caller voice...")
        play_t = play_async(pcm_22k, SPEAKER_RATE, "caller")

        # ── LEG 2a: Stream caller PCM to gateway while it plays ───────────────
        print(f"  │ 📡 LEG 2 — Streaming to gateway ({GATEWAY_HOST}:{GATEWAY_PORT})...")
        FRAME = 320   # 20ms @ 8 kHz s16le
        try:
            for i in range(0, len(pcm_8k), FRAME):
                if writer.is_closing():
                    break
                frame = pcm_8k[i : i + FRAME]
                if len(frame) < FRAME:
                    frame = frame.ljust(FRAME, b"\x00")
                writer.write(struct.pack("!BH", 0x10, FRAME) + frame)
                master_audio_frames.append(frame)
                await asyncio.sleep(0.019)
            # 700ms trailing silence → triggers VAD endpointing
            silence = b"\x00" * FRAME
            for _ in range(35):
                if writer.is_closing():
                    break
                writer.write(struct.pack("!BH", 0x10, FRAME) + silence)
                master_audio_frames.append(silence)
                await asyncio.sleep(0.019)
            if not writer.is_closing():
                await writer.drain()
        except Exception:
            pass

        # Make sure speaker finished the caller voice before bot answers
        play_t.join()

        # ── LEG 2b: Receive and play bot audio live ───────────────────────────
        print(f"  │ ⏳ Waiting for bot reply...")
        t_resp        = time.perf_counter()
        bot_audio     = bytearray()
        bot_play_buf  = bytearray()
        first_audio_t = None
        PLAY_CHUNK    = 16000   # play every ~1s of bot audio for low-latency feel

        import sounddevice as sd
        try:
            sd_stream = sd.RawOutputStream(
                samplerate=BOT_RATE,
                channels=1,
                dtype="int16",
                blocksize=320,
            )
            sd_stream.start()
            speaker_ok = True
        except Exception as ex:
            print(f"  │ [⚠️  Speaker stream failed — {ex}]")
            sd_stream  = None
            speaker_ok = False

        while time.perf_counter() - t_resp < 3.5:
            try:
                chunk = await asyncio.wait_for(rx_queue.get(), timeout=0.35)
                if first_audio_t is None:
                    first_audio_t = time.perf_counter() - t_resp
                bot_audio.extend(chunk)
                master_audio_frames.append(chunk)
                # Stream each chunk to speakers as it arrives
                if speaker_ok and sd_stream:
                    try:
                        sd_stream.write(chunk)
                    except Exception:
                        pass
            except (asyncio.TimeoutError, TimeoutError):
                if len(bot_audio) > 1600:
                    break  # enough audio + silence gap → done

        if sd_stream:
            try:
                sd_stream.stop()
                sd_stream.close()
            except Exception:
                pass

        # Play full bot reply through Windows system speakers
        if len(bot_audio) > 1600:
            play_t = play_async(bytes(bot_audio), BOT_RATE, "bot")
            play_t.join()

        total_turn_ms = (time.perf_counter() - t_resp) * 1000.0
        bot_dur_s     = len(bot_audio) / 16000.0
        ttfa_ms       = (first_audio_t or 0.0) * 1000.0
        print(f"  │ 🔊 LEG 2 — Bot replied: {bot_dur_s:.2f}s  TTFA={ttfa_ms:.0f}ms  Total={total_turn_ms:.0f}ms")

        # ── LEG 3: Transcribe bot audio back to text ──────────────────────────
        print(f"  │ 🎧 LEG 3 — Transcribing bot audio via STT...")
        t_stt = time.perf_counter()
        bot_text = await transcribe_bot_audio(bytes(bot_audio), label=f"{persona['id']}_T{turn_idx}", lang=lang)
        stt_ms   = (time.perf_counter() - t_stt) * 1000.0
        if bot_text:
            print(f"  │ 📝 BOT SAID: \"{bot_text}\"  ({stt_ms:.0f}ms)")
        else:
            print(f"  │ 📝 BOT SAID: (no transcript)  ({stt_ms:.0f}ms)")
        print(f"  └{'─'*60}")

        # ── Record telemetry ──────────────────────────────────────────────────
        all_telemetry.append({
            "episode":        persona["id"],
            "episode_title":  persona["title"],
            "turn":           turn_idx,
            "lang":           lang,
            "customer_text":  text,
            "caller_dur_s":   round(caller_dur, 2),
            "tts_synth_ms":   round(synth_ms, 1),
            "bot_audio_s":    round(bot_dur_s, 2),
            "ttfa_ms":        round(ttfa_ms, 1),
            "total_turn_ms":  round(total_turn_ms, 1),
            "bot_transcript": bot_text,
            "bot_stt_ms":     round(stt_ms, 1),
        })
        _flush_telemetry(all_telemetry)

        await asyncio.sleep(0.8)

    # ── Hangup ────────────────────────────────────────────────────────────────
    session_alive = False
    try:
        writer.write(struct.pack("!BH", 0x00, 0))
        await writer.drain()
        writer.close()
        await writer.wait_closed()
    except Exception:
        pass
    receiver_task.cancel()
    print(f"\n  ✅ Episode {persona['id']} complete.\n")


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
async def main():
    print()
    print("█" * 80)
    print("  SUPERFONE  —  VOICE → VOICE → VOICE  LIVE SIMULATION")
    print("  You will HEAR every word: caller and bot, through your speakers.")
    print(f"  Gateway  : {GATEWAY_HOST}:{GATEWAY_PORT}")
    print(f"  STT      : {STT_URL}")
    print(f"  Episodes : {len(CUSTOMER_PERSONAS)}  (EN + HI bilingual)")
    print("█" * 80)

    all_telemetry: list     = []
    master_audio_frames: list = []
    t_start = time.perf_counter()

    for idx, persona in enumerate(CUSTOMER_PERSONAS, 1):
        await run_episode(persona, idx, len(CUSTOMER_PERSONAS), all_telemetry, master_audio_frames)
        if idx < len(CUSTOMER_PERSONAS):
            print("  ⏸  3 second pause before next episode...\n")
            await asyncio.sleep(3.0)

    total_min = (time.perf_counter() - t_start) / 60.0
    print()
    print("█" * 80)
    print(f"  SIMULATION COMPLETE  —  {total_min:.1f} min  |  {len(all_telemetry)} turns")
    print("█" * 80)

    # Save master WAV
    master_wav = os.path.join(ART_DIR, "simulation_master_recording.wav")
    raw_all = b"".join(master_audio_frames)
    with wave.open(master_wav, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(8000)
        wf.writeframes(raw_all)
    print(f"\n💾 Master recording : {master_wav}")
    print(f"   Duration         : {len(raw_all)/16000.0/60.0:.2f} min")

    _flush_telemetry(all_telemetry)
    print(f"📊 Telemetry JSON   : {os.path.join(ART_DIR, 'simulation_telemetry.json')}")

    # Summary table
    print()
    print("┌─────────────────────────────────────────────────────────────────────────────────────────────────────")
    print(f"│ {'EP':<6} {'T':<3} {'LANG':<5} {'CALLER_S':<9} {'BOT_S':<7} {'TTFA_ms':<9} {'TOTAL_ms':<10} BOT SAID")
    print("├─────────────────────────────────────────────────────────────────────────────────────────────────────")
    for r in all_telemetry:
        snippet = (r["bot_transcript"] or "—")[:55]
        print(
            f"│ {r['episode']:<6} {r['turn']:<3} {r['lang']:<5} "
            f"{r['caller_dur_s']:<9.2f} {r['bot_audio_s']:<7.2f} "
            f"{r['ttfa_ms']:<9.0f} {r['total_turn_ms']:<10.0f} {snippet}"
        )
    print("└─────────────────────────────────────────────────────────────────────────────────────────────────────")


if __name__ == "__main__":
    asyncio.run(main())
