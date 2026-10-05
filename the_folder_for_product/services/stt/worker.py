import os
import time
import asyncio
import re
from pathlib import Path
from dotenv import load_dotenv

# Follow Multi-Path .env Resolution Rule
_env_paths = [
    Path(__file__).parent / ".env",
    Path(__file__).parent.parent / ".env",
    Path(__file__).parent.parent.parent / ".env",
    Path("c:/daily_works/superfone_call/.env")
]
for _ep in _env_paths:
    if _ep.exists():
        load_dotenv(str(_ep), override=True)
        break

import httpx

_http_client = None

def _get_http() -> httpx.Client:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.Client(
            timeout=httpx.Timeout(4.5, connect=2.5),
            limits=httpx.Limits(max_keepalive_connections=20, max_connections=50, keepalive_expiry=120.0),
        )
    return _http_client

from concurrent.futures import ProcessPoolExecutor
from aiohttp import web
import numpy as np
from scipy.signal import resample_poly
try:
    from faster_whisper import WhisperModel
except ImportError:
    WhisperModel = None

# Global variable inside each worker process
whisper_model = None

def init_worker():
    """Pool initializer. In 3-API cloud mode, skip loading local CPU whisper model."""
    global whisper_model
    if os.environ.get("GROQ_API_KEY") or os.environ.get("DEEPGRAM_API_KEY"):
        whisper_model = None
        return
    if WhisperModel is None:
        return
    os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
    model_name = os.environ.get("WHISPER_MODEL", "base")
    try:
        whisper_model = WhisperModel(model_name, device="cpu", compute_type="int8", cpu_threads=6)
        print(f"[STT Worker {os.getpid()}] Multilingual Model ({model_name}) loaded once at process startup.")
    except Exception as ex:
        print(f"[STT Worker {os.getpid()}] Local model warning: {ex}")
        whisper_model = None

def detect_repetition(text: str) -> tuple[bool, str, int]:
    """Detect runaway n-gram repetition loops in speech transcripts."""
    words = re.findall(r"[a-zA-Z0-9']+", text.lower())
    if len(words) < 6:
        return False, "", 0

    # Detect repeated phrases of 1–5 words
    for phrase_size in range(1, 6):
        for i in range(len(words) - phrase_size * 3 + 1):
            phrase = words[i:i + phrase_size]
            if words[i:i + phrase_size * 3] == phrase * 3:
                k = 0
                while i + (k + 1) * phrase_size <= len(words) and words[i + k * phrase_size:i + (k + 1) * phrase_size] == phrase:
                    k += 1
                return True, " ".join(phrase), k

_HALLUCINATION_EXACT = {
    "thank you", "thanks", "amen", "you", "bye", "subtitles",
    "झाल", "झाल झाल", "झाला", "झालं", "बख़जब", "बघितल्याबद्दल धन्यवाद", "धन्यवाद"
}

def is_hallucination_text(tx: str, lang: str = "en") -> bool:
    if not tx or not tx.strip():
        return True
    cleaned = tx.strip().lower().rstrip('.!,?।')
    if cleaned in _HALLUCINATION_EXACT:
        return True
    if any(c in cleaned for c in "ðþæø"):
        return True
    parts = cleaned.split()
    if len(parts) >= 2 and all(p == parts[0] for p in parts) and parts[0] in ("झाल", "झाला", "बख़जब"):
        return True
    return False

def transcribe_audio(audio_pcm16_8k: bytes, enqueue_time: float, language: str = "en") -> dict:
    """
    Runs inside the worker process.

    Timing boundaries:
      queue_wait_ms  — wall-clock time from HTTP handler enqueue to worker task start.
                       Uses time.time() (wall clock) for cross-process consistency;
                       perf_counter is process-local on some platforms.
      preprocess_ms  — 8 kHz→16 kHz resample + float32 normalize.
      inference_ms   — Whisper transcribe() call only.
    """
    # Queue wait: wall-clock delta from caller's enqueue timestamp
    worker_start_time = time.time()
    queue_wait_ms = (worker_start_time - enqueue_time) * 1000.0

    global whisper_model
    
    # ⚡ 1. PRIMARY ULTRA-FAST CLOUD STT: GROQ WHISPER-LARGE-V3-TURBO & DEEPGRAM NOVA-2 (~250ms)
    groq_key = os.environ.get("GROQ_API_KEY", "")
    deepgram_key = os.environ.get("DEEPGRAM_API_KEY", "")

    if groq_key or deepgram_key:
        try:
            import io, wave
            wav_io = io.BytesIO()
            with wave.open(wav_io, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(8000)
                wf.writeframes(audio_pcm16_8k)
            wav_mem = wav_io.getvalue()
            http_cli = _get_http()

            if groq_key:
                try:
                    # Strip dialect specific codes if present for Groq (e.g. en-IN -> en)
                    groq_lang = language.split("-")[0] if language else "en"
                    # Only pass language if it's not marwadi since whisper doesn't have marwadi code
                    groq_data = {"model": "whisper-large-v3-turbo", "language": "hi" if groq_lang == "marwadi" else groq_lang}
                    if groq_lang == "marwadi":
                        groq_data["prompt"] = "खम्मा घणी, म्हारो, थांकी, अठे, कठे, काई, सा, पण, मारवाड़ी, बता, होगे, मने, पाछो, सको"
                    elif groq_lang == "hi":
                        groq_data["prompt"] = "नमस्ते, हैलो, हाँ जी, बताइए, आप क्या कह रहे हैं, मैं सुन रही हूँ।"

                    res = http_cli.post(
                        "https://api.groq.com/openai/v1/audio/transcriptions",
                        headers={"Authorization": f"Bearer {groq_key}"},
                        files={"file": ("speech.wav", wav_mem, "audio/wav")},
                        data=groq_data,
                    )
                    if res.status_code == 200:
                        tx = res.json().get("text", "").strip()
                        if tx and not is_hallucination_text(tx, groq_lang):
                            inf_ms = (time.time() - worker_start_time) * 1000.0
                            return {"text": tx, "confidence": 0.98, "avg_logprob": -0.1, "no_speech_prob": 0.0, "compression_ratio": 1.0, "audio_duration_ms": len(audio_pcm16_8k)/16.0, "queue_wait_ms": queue_wait_ms, "preprocess_ms": 1.0, "inference_ms": inf_ms, "worker_pid": os.getpid()}
                    else:
                        print(f"[STT Worker] Groq HTTP {res.status_code}: {res.text[:120]}")
                except Exception as ex:
                    print(f"[STT Worker] Groq error: {ex}")

            if deepgram_key:
                try:
                    dg_lang = language.split("-")[0] if language else "en"
                    dg_lang = "hi" if dg_lang == "marwadi" else dg_lang
                    res = http_cli.post(
                        f"https://api.deepgram.com/v1/listen?model=nova-2&smart_format=true&language={dg_lang}",
                        headers={"Authorization": f"Token {deepgram_key}", "Content-Type": "audio/wav"},
                        content=wav_mem,
                    )
                    if res.status_code == 200:
                        tx = res.json()["results"]["channels"][0]["alternatives"][0]["transcript"].strip()
                        if tx and not is_hallucination_text(tx, dg_lang):
                            inf_ms = (time.time() - worker_start_time) * 1000.0
                            return {"text": tx, "confidence": 0.98, "avg_logprob": -0.1, "no_speech_prob": 0.0, "compression_ratio": 1.0, "audio_duration_ms": len(audio_pcm16_8k)/16.0, "queue_wait_ms": queue_wait_ms, "preprocess_ms": 1.0, "inference_ms": inf_ms, "worker_pid": os.getpid()}
                    else:
                        print(f"[STT Worker] Deepgram HTTP {res.status_code}: {res.text[:120]}")
                except Exception as ex:
                    print(f"[STT Worker] Deepgram error: {ex}")
        except Exception as ex:
            print(f"[STT Worker] Cloud STT error: {ex}")

        # In cloud-first mode, if both Groq and Deepgram failed, do not block CPU with local Whisper
        return {
            "text": "",
            "confidence": 0.0,
            "avg_logprob": -99.0,
            "no_speech_prob": 1.0,
            "compression_ratio": 1.0,
            "audio_duration_ms": len(audio_pcm16_8k) / 16.0,
            "queue_wait_ms": queue_wait_ms,
            "preprocess_ms": 0.0,
            "inference_ms": (time.time() - worker_start_time) * 1000.0,
            "worker_pid": os.getpid()
        }

    if whisper_model is None:
        init_worker()

    try:
        # ── Preprocessing ────────────────────────────────────────────────────
        t_pre = time.perf_counter()
        samples = np.frombuffer(audio_pcm16_8k, dtype=np.int16)
        if len(samples) == 0:
            return {"text": "", "confidence": 0.0, "avg_logprob": -99.0, "no_speech_prob": 1.0, "compression_ratio": 1.0, "audio_duration_ms": 0.0, "queue_wait_ms": queue_wait_ms, "preprocess_ms": 0.0, "inference_ms": 0.0, "worker_pid": os.getpid()}

        # Polyphase upsample 8 kHz → 16 kHz (ratio 2/1)
        samples_16k = resample_poly(samples, 2, 1)
        # Normalize to float32
        audio_float32 = samples_16k.astype(np.float32) / 32768.0
        preprocess_ms = (time.perf_counter() - t_pre) * 1000.0

        # ── Inference ────────────────────────────────────────────────────────
        t_inf = time.perf_counter()
        audio_duration_s = len(samples) / 8000.0
        audio_duration_ms = audio_duration_s * 1000.0

        segments, info = whisper_model.transcribe(
            audio_float32,
            beam_size=1,
            best_of=1,
            temperature=0.0,
            vad_filter=True,
            without_timestamps=True,
            condition_on_previous_text=False,
            compression_ratio_threshold=4.5,
            log_prob_threshold=-1.0,
            no_speech_threshold=0.4,
            initial_prompt="Namaste, hello, natural open conversation in English and Hindi.",
        )

        text_parts = []
        confidences = []
        logprobs = []
        no_speech_probs = []
        compression_ratios = []

        for segment in segments:
            text_parts.append(segment.text)
            conf = float(np.exp(segment.avg_logprob))
            confidences.append(conf)
            logprobs.append(segment.avg_logprob)
            no_speech_probs.append(segment.no_speech_prob)
            compression_ratios.append(segment.compression_ratio)

        raw_stt_text = "".join(text_parts).strip()
        normalized_stt_text = re.sub(r'\s+', ' ', raw_stt_text).strip()

        # Flag suspicious script glitches (Arabic/Urdu/Chinese) for audit without silent deletion
        suspicious_scripts = re.findall(r'[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\u4E00-\u9FFF]', raw_stt_text)
        if suspicious_scripts:
            print(f"[STT Worker {os.getpid()}] SUSPICIOUS_SCRIPT_DETECTED count={len(suspicious_scripts)} text='{raw_stt_text}'")
            llm_consumed_text = re.sub(r'[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\u4E00-\u9FFF]', '', raw_stt_text).strip()
        else:
            llm_consumed_text = normalized_stt_text

        text = llm_consumed_text

        if text.strip() and not is_hallucination_text(text, language):
            confidence = max(0.85, float(np.mean(confidences)) if confidences else 0.85)
        else:
            confidence = 0.0
        avg_logprob = float(np.mean(logprobs)) if logprobs else -99.0
        no_speech_prob = float(np.mean(no_speech_probs)) if no_speech_probs else 0.0
        compression_ratio = float(np.mean(compression_ratios)) if compression_ratios else 1.0

        # 1. Repetition loop guard: detect and discard runaway hallucinations
        is_repetitive, rep_phrase, rep_count = detect_repetition(text)
        if is_repetitive:
            words_count = len(re.findall(r"[a-zA-Z0-9']+", text))
            print(f"[STT Worker {os.getpid()}] STT_REJECTED reason=repetition word_count={words_count} repeated_phrase='{rep_phrase}' repeat_count={rep_count}")
            text = ""

        # 2. Compression ratio guard: runaway text has high compression ratios (>4.5)
        if compression_ratio > 4.5 and avg_logprob < -0.8:
            print(f"[STT Worker {os.getpid()}] STT_REJECTED reason=compression_ratio_exceeded ratio={compression_ratio:.2f}")
            text = ""

        # 3. Soft Hallucination Filter (Preserves short speech like "Alo", "Hello", "Haan", "Ji")
        is_soft_hallucination = False
        reject_reason = ""

        if no_speech_prob > 0.85: # Only reject when Whisper is 85%+ certain there is zero speech
            is_soft_hallucination = True
            reject_reason = "no_speech_probability"
        elif len(text.strip()) == 0:
            is_soft_hallucination = True
            reject_reason = "empty_text"

        if is_soft_hallucination and text:
            print(
                f"[STT Worker {os.getpid()}] STT_REJECTED reason={reject_reason} "
                f"text='{text}' confidence={confidence:.3f} no_speech_prob={no_speech_prob:.3f} avg_logprob={avg_logprob:.3f}"
            )
            text = ""

        inference_ms = (time.perf_counter() - t_inf) * 1000.0

        return {
            "text": text,
            "confidence": confidence,
            "avg_logprob": round(avg_logprob, 3),
            "no_speech_prob": round(no_speech_prob, 3),
            "compression_ratio": round(compression_ratio, 3),
            "audio_duration_ms": round(audio_duration_ms, 1),
            "queue_wait_ms": round(queue_wait_ms, 3),
            "preprocess_ms": round(preprocess_ms, 3),
            "inference_ms": round(inference_ms, 3),
            "worker_pid": os.getpid(),
        }
    except Exception as e:
        print(f"[STT Worker {os.getpid()}] Error during transcription: {e}")
        return {"text": "", "confidence": 0.0,
                "avg_logprob": -99.0, "no_speech_prob": 1.0, "compression_ratio": 1.0,
                "audio_duration_ms": 0.0,
                "queue_wait_ms": queue_wait_ms, "preprocess_ms": 0.0, "inference_ms": 0.0,
                "worker_pid": os.getpid()}



from concurrent.futures import ThreadPoolExecutor

class STTServer:
    def __init__(self, host="127.0.0.1", port=9094, workers=2):
        self.host = host
        self.port = port
        self.workers = workers
        self.executor = None

    async def start(self):
        global whisper_model
        model_name = os.environ.get("WHISPER_MODEL", "base.en")
        if WhisperModel:
            try:
                print(f"[STT Server] Loading Faster-Whisper ({model_name}) once at server startup...")
                whisper_model = WhisperModel(model_name, device="cpu", compute_type="int8", cpu_threads=4)
                print(f"[STT Server] Model ({model_name}) loaded successfully.")
            except Exception as e:
                print(f"[STT Server] Faster-Whisper load warning ({e}). Active mode: Groq Cloud whisper-large-v3-turbo / Deepgram fallback.")
                whisper_model = None
        else:
            print(f"[STT Server] Faster-Whisper not installed. Active mode: Groq Cloud whisper-large-v3-turbo / Deepgram fallback.")

        self.executor = ThreadPoolExecutor(max_workers=self.workers)
        # Pre-warm with a dummy inference
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(self.executor, transcribe_audio, b"\x00" * 3200, time.time())
        print(f"[STT Server] Pre-warmup complete. Ready for real-time requests.")

        app = web.Application()
        app.router.add_post("/stt", self.handle_stt)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, self.host, self.port)
        await site.start()
        print(f"STT Server listening on http://{self.host}:{self.port}/stt with {self.workers} workers")

    async def handle_stt(self, request):
        t_handler_start = time.perf_counter()
        # Wall-clock enqueue time passed to worker for cross-process queue-wait measurement
        enqueue_time = float(request.headers.get("X-Enqueue-Time", str(time.time())))
        language = request.headers.get("X-Language", "en")
        audio_data = await request.read()

        loop = asyncio.get_running_loop()
        try:
            result = await loop.run_in_executor(
                self.executor, transcribe_audio, audio_data, enqueue_time, language
            )
        except Exception as e:
            print(f"STT Service Error: {e}")
            result = {"text": "", "confidence": 0.0,
                      "queue_wait_ms": 0.0, "preprocess_ms": 0.0, "inference_ms": 0.0,
                      "worker_pid": 0}

        latency_ms = (time.perf_counter() - t_handler_start) * 1000.0
        return web.json_response({
            "text": result["text"],
            "confidence": result["confidence"],
            "queue_wait_ms": result["queue_wait_ms"],
            "preprocess_ms": result["preprocess_ms"],
            "inference_ms": result["inference_ms"],
            "worker_pid": result.get("worker_pid", 0),
            "latency_ms": round(latency_ms, 3),
        }, headers={
            "X-Worker-PID": str(result.get("worker_pid", 0))
        })


    def shutdown(self):
        if self.executor:
            self.executor.shutdown()


if __name__ == '__main__':
    workers = int(os.environ.get("STT_WORKERS", "2"))
    server = STTServer(workers=workers)
    loop = asyncio.new_event_loop()

    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(server.start())
        loop.run_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
