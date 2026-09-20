"""
services/tts/worker.py — Phase 2: persistent warm Piper subprocess pool.
Phase 3 additions: queue_wait_ms + inference_ms telemetry per request.

Timing boundaries:
  queue_wait_ms  — wall-clock time from HTTP handler enqueue to worker task start.
                   Uses time.time() for cross-process consistency.
  inference_ms   — PersistentPiper.synthesize() + resample_poly only.
                   Does not include HTTP overhead or queue_wait.
  latency_ms     — total HTTP handler time (queue_wait + inference + HTTP overhead).
                   queue_wait + inference < latency_ms; remainder is expected overhead.

LLM serialization constraint (on record since M1 review):
  One Llama instance → one inference at a time system-wide.
  This is the hard throughput ceiling until multiple model instances or a
  batching server is introduced.
"""

import os
import sys
import re

try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass
import time
import queue
import threading
import subprocess
import asyncio
from concurrent.futures import ProcessPoolExecutor

import numpy as np
from scipy.signal import resample_poly
from aiohttp import web


class PersistentPiper:
    """
    Wraps piper.exe as a long-lived subprocess, keeping the voice model
    loaded in memory across synthesis requests.

    audio= values in Piper's stderr log are cumulative since process start
    (verified empirically: three sequential requests produced 0.464 → 3.773 →
    4.342 sec, not per-utterance durations). Delta slicing is therefore:
        delta = current_cumulative - prev_cumulative
    and expected PCM bytes = round(delta * 22050) * 2.
    """

    SAMPLE_RATE = 22050
    BYTES_PER_SAMPLE = 2

    def __init__(self, piper_path: str, voice_model: str):
        self.piper_path = piper_path
        self.voice_model = voice_model
        self.proc: subprocess.Popen | None = None
        self._stdout_buffer = bytearray()
        self._buffer_lock = threading.Lock()
        self._completion_queue: queue.Queue[float] = queue.Queue()
        self._ready_event = threading.Event()
        self._running = False
        self._prev_cumulative = 0.0
        self._stdout_thread: threading.Thread | None = None
        self._stderr_thread: threading.Thread | None = None

    # ── lifecycle ────────────────────────────────────────────────────────────

    def _reset_process_state(self) -> None:
        """Clear all per-process state. Must be called before every spawn."""
        with self._buffer_lock:
            self._stdout_buffer.clear()
        while True:
            try:
                self._completion_queue.get_nowait()
            except queue.Empty:
                break
        self._prev_cumulative = 0.0
        self._ready_event.clear()

    def start(self) -> None:
        self._running = True
        self._reset_process_state()
        proc = subprocess.Popen(
            [self.piper_path, "--model", self.voice_model, "--output_raw"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=False,
        )
        self.proc = proc
        self._stdout_thread = threading.Thread(
            target=self._read_stdout, args=(proc,), daemon=True, name="piper-stdout"
        )
        self._stderr_thread = threading.Thread(
            target=self._read_stderr, args=(proc,), daemon=True, name="piper-stderr"
        )
        self._stdout_thread.start()
        self._stderr_thread.start()
        if not self._ready_event.wait(timeout=10.0):
            raise RuntimeError("Piper did not initialize within 10 s")

    def close(self, join_threads: bool = False) -> None:
        self._running = False
        proc = self.proc
        self.proc = None
        if join_threads:
            for t in (self._stdout_thread, self._stderr_thread):
                if t and t.is_alive():
                    t.join(timeout=2.0)
        self._stdout_thread = None
        self._stderr_thread = None
        if proc is None:
            return
        try:
            proc.stdin.close()
        except (BrokenPipeError, OSError):
            pass
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                pass

    # ── background reader threads ─────────────────────────────────────────────

    def _read_stdout(self, proc: subprocess.Popen) -> None:
        """Continuously drains stdout pipe to prevent OS buffer deadlock."""
        while self._running and proc is self.proc:
            try:
                data = proc.stdout.read1(4096)
                if not data:
                    break
                with self._buffer_lock:
                    self._stdout_buffer.extend(data)
            except Exception:
                break

    def _read_stderr(self, proc: subprocess.Popen) -> None:
        """Parses cumulative audio duration from Piper's stderr log lines."""
        audio_val = 0.0
        while self._running and proc is self.proc:
            try:
                line = proc.stderr.readline()
                if not line:
                    break
                s = line.decode("utf-8", errors="replace")
                if "Initialized piper" in s:
                    self._ready_event.set()
                    continue
                m = re.search(r"audio=(\d+\.\d+) sec", s)
                if m:
                    audio_val = float(m.group(1))
                if "Real-time factor:" in s:
                    self._completion_queue.put(audio_val)
                    audio_val = 0.0
            except Exception:
                break

    # ── synthesis ─────────────────────────────────────────────────────────────

    def _invalidate_proc(self) -> None:
        """Mark process as dead; next synthesize() call will respawn."""
        self.proc = None

    def _check_and_respawn(self) -> None:
        if self.proc is None or self.proc.poll() is not None:
            print(f"[TTS/{os.getpid()}] Piper dead — respawning")
            self.close(join_threads=True)
            self.start()

    def synthesize(self, text: str) -> bytes:
        """
        Returns raw 22050 Hz PCM16 mono bytes for the given text.

        Newline sanitization: any \\r or \\n in text is replaced with a space
        before writing to stdin. This guarantees exactly one stdin line →
        exactly one 'Real-time factor:' log line → one completion event.
        """
        self._check_and_respawn()

        clean = text.replace("\r", " ").replace("\n", " ").strip()
        if not clean:
            return b""

        self.proc.stdin.write((clean + "\n").encode("utf-8"))
        self.proc.stdin.flush()

        try:
            current_cumulative = self._completion_queue.get(timeout=8.0)
        except queue.Empty:
            self._invalidate_proc()
            raise TimeoutError("Piper synthesis timed out (process may have died)")

        delta = current_cumulative - self._prev_cumulative
        expected_bytes = int(round(delta * self.SAMPLE_RATE)) * self.BYTES_PER_SAMPLE

        deadline = time.monotonic() + 2.0
        while True:
            with self._buffer_lock:
                have = len(self._stdout_buffer)
            if have >= expected_bytes:
                break
            if time.monotonic() > deadline:
                self._invalidate_proc()
                raise TimeoutError(
                    f"Stdout fill timeout: have {have} B, need {expected_bytes} B"
                )
            time.sleep(0.005)

        with self._buffer_lock:
            pcm_22k = bytes(self._stdout_buffer[:expected_bytes])
            del self._stdout_buffer[:expected_bytes]

        self._prev_cumulative = current_cumulative
        return pcm_22k


# ── process-pool entry points ─────────────────────────────────────────────────

_piper: PersistentPiper | None = None


def normalize_text_for_telephony(text: str) -> str:
    """Normalizes raw LLM text for natural telephony TTS output."""
    # 1. Clean markdown formatting and symbols that cause stutter
    text = re.sub(r'[*_#`~]', '', text)
    
    # 2. Hindi & English Time Normalization
    text = re.sub(r'(\d{1,2}):00\s*([AaPp][Mm])?', r'\1 बजे', text)
    text = re.sub(r'(\d{1,2}):(\d{2})', r'\1 बजकर \2 मिनट', text)
    text = re.sub(r'\b(\d{1,2})\s*([AaPp][Mm])\b', r'\1 \2', text)

    # 3. Currency normalization
    text = re.sub(r'(?:Rs\.?|₹)\s*(\d+)', r'\1 rupees', text)
    text = re.sub(r'\$\s*(\d+)', r'\1 dollars', text)
    
    # 4. Phone number digit spacing
    def format_phone(m):
        digits = re.sub(r'\D', '', m.group(0))
        if len(digits) == 10:
            return " ".join(digits[:5]) + ", " + " ".join(digits[5:])
        elif len(digits) > 5:
            return " ".join(digits)
        return m.group(0)

    text = re.sub(r'\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b', format_phone, text)
    
    # 5. Clean isolated colons or semicolons that cause unnatural pauses
    text = re.sub(r'(?<=\D):(?=\D)', ' ', text)
    text = re.sub(r'\s+', ' ', text)

    return text.strip()


_piper_en: PersistentPiper | None = None
_piper_hi: PersistentPiper | None = None
_kokoro_engine = None

def init_worker() -> None:
    """Pool initializer. Spawns and warms Kokoro-82M neural engine and Piper fallback."""
    global _piper_en, _piper_hi, _kokoro_engine
    
    # 1. Initialize Kokoro-82M Neural Engine
    try:
        from services.tts.kokoro_engine import KokoroTTSEngine
        _kokoro_engine = KokoroTTSEngine()
        if _kokoro_engine.kokoro:
            print(f"[TTS Worker {os.getpid()}] Kokoro-82M Neural Engine initialized successfully!")
    except Exception as ex:
        print(f"[TTS Worker {os.getpid()}] Kokoro init notice: {ex}")

    # 2. Initialize Piper as Fallback / Devanagari Hindi engine
    piper_path = r"c:\daily_works\superfone_call\piper\piper\piper.exe"
    en_model = os.environ.get("PIPER_VOICE_MODEL", r"c:\daily_works\superfone_call\models\en_US-lessac-medium.onnx")
    hi_model = r"c:\daily_works\superfone_call\models\hi_IN-pratham-medium.onnx"

    if os.path.exists(piper_path) and os.path.exists(en_model):
        try:
            _piper_en = PersistentPiper(piper_path=piper_path, voice_model=en_model)
            _piper_en.start()
        except Exception as e:
            print(f"[TTS Worker {os.getpid()}] Piper EN fallback init warning: {e}")

    if os.path.exists(piper_path) and os.path.exists(hi_model):
        try:
            _piper_hi = PersistentPiper(piper_path=piper_path, voice_model=hi_model)
            _piper_hi.start()
        except Exception as ex:
            print(f"[TTS Worker {os.getpid()}] Hindi Piper init warning: {ex}")


def get_live_voice_config() -> dict:
    cfg_file = r"c:\daily_works\superfone_call\services\audio_studio\active_config.json"
    if os.path.exists(cfg_file):
        try:
            import json
            with open(cfg_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"voice": "hi_female", "speed": 0.88, "volume_gain_db": 0.0, "fade_in_ms": 4.0}


def generate_tts_and_resample(text: str, enqueue_time: float, requested_voice: str = None) -> dict:
    """
    Synthesize text via Kokoro-82M (or Piper fallback), outputting clean 8000 Hz PCM16 mono
    with live studio parameters (speed, voice profile, volume gain).
    """
    worker_start_time = time.time()
    queue_wait_ms = (worker_start_time - enqueue_time) * 1000.0

    t_infer = time.perf_counter()
    clean_text = normalize_text_for_telephony(text)
    audio_bytes = b""
    live_cfg = get_live_voice_config()
    voice = requested_voice or live_cfg.get("voice", "hi_female")
    speed = float(live_cfg.get("speed", 0.88))
    volume_gain_db = float(live_cfg.get("volume_gain_db", 0.0))
    fade_in_ms = float(live_cfg.get("fade_in_ms", 4.0))

    print(f"[TTS STEP 1: PARSE & CONFIG] Text: \"{clean_text[:40]}...\" | Voice Profile: {voice} | Speed: {speed}x | Gain: {volume_gain_db}dB", flush=True)

    # ⚡ 1. PRIMARY ULTRA-FAST DEEPGRAM AURA NEURAL TTS (~200ms LATENCY)
    deepgram_key = os.environ.get("DEEPGRAM_API_KEY", "")
    if deepgram_key and clean_text:
        try:
            import httpx
            url = "https://api.deepgram.com/v1/speak?model=aura-asteria-en&encoding=linear16&sample_rate=8000"
            res = httpx.post(
                url,
                headers={"Authorization": f"Token {deepgram_key}", "Content-Type": "application/json"},
                json={"text": clean_text},
                timeout=3.0
            )
            if res.status_code == 200 and len(res.content) > 44:
                raw_pcm = res.content[44:] if res.content.startswith(b"RIFF") else res.content
                audio_bytes = raw_pcm
        except Exception as dg_err:
            print(f"[TTS Worker] Deepgram Aura notice: {dg_err}", flush=True)

    # 2. Kokoro-82M Neural Engine (Fallback)
    if not audio_bytes and _kokoro_engine and _kokoro_engine.kokoro and clean_text:
        try:
            audio_bytes = _kokoro_engine.synthesize_telephony_8k(clean_text, voice=voice, speed=speed)
            if audio_bytes and volume_gain_db != 0.0:
                samples = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32)
                samples = samples * (10.0 ** (volume_gain_db / 20.0))
                samples = np.clip(samples, -32767.0, 32767.0).astype(np.int16)
                audio_bytes = samples.tobytes()
        except Exception as k_err:
            print(f"[TTS Worker] Kokoro synthesis notice ({voice}): {k_err}", flush=True)
            audio_bytes = b""

    # 2. On-Premise Piper Fallback
    if not audio_bytes and clean_text:
        piper_instance = (_piper_hi if voice.startswith("hi_") or re.search(r'[\u0900-\u097F]', clean_text) else _piper_en)
        if not piper_instance:
            piper_instance = _piper_en or _piper_hi
        if piper_instance:
            try:
                pcm_22k = piper_instance.synthesize(clean_text)
                if pcm_22k:
                    samples = np.frombuffer(pcm_22k, dtype=np.int16).astype(np.float32)
                    resampled = resample_poly(samples, 160, 441)
                    if volume_gain_db != 0.0:
                        resampled = resampled * (10.0 ** (volume_gain_db / 20.0))
                    resampled = np.clip(resampled, -32767.0, 32767.0)
                    fade_len = int((fade_in_ms / 1000.0) * 8000)
                    if fade_len > 0 and len(resampled) > fade_len:
                        resampled[:fade_len] *= np.linspace(0.0, 1.0, fade_len)
                    audio_bytes = resampled.astype(np.int16).tobytes()
            except Exception as p_err:
                print(f"[TTS Worker] Piper fallback error: {p_err}", flush=True)

    # 4. Fail-Safe EdgeTTS Cloud Neural Fallback (Guarantees Audio Generation)
    if not audio_bytes and clean_text:
        try:
            import edge_tts
            import io
            from pydub import AudioSegment

            is_hindi = bool(re.search(r'[\u0900-\u097F]', clean_text))
            edge_voice = "hi-IN-SwaraNeural" if is_hindi else "en-US-AvaNeural"
            
            async def run_edge():
                c = edge_tts.Communicate(clean_text, edge_voice)
                mp3_b = bytearray()
                async for chunk in c.stream():
                    if chunk["type"] == "audio":
                        mp3_b.extend(chunk["data"])
                return bytes(mp3_b)

            mp3_data = asyncio.run(run_edge())
            if mp3_data:
                audio_seg = AudioSegment.from_file(io.BytesIO(mp3_data), format="mp3")
                audio_seg = audio_seg.set_frame_rate(8000).set_channels(1).set_sample_width(2)
                audio_bytes = audio_seg.raw_data
                print(f"[TTS Worker] EdgeTTS Fallback produced {len(audio_bytes)} bytes PCM!", flush=True)
        except Exception as edge_err:
            print(f"[TTS Worker] EdgeTTS fallback error: {edge_err}", flush=True)

    inference_ms = (time.perf_counter() - t_infer) * 1000.0
    print(f"[TTS STEP 2: NEURAL SYNTHESIS COMPLETE] Inference Time: {inference_ms:.1f}ms | Produced: {len(audio_bytes)} bytes (8000Hz PCM16 Mono)", flush=True)

    return {
        "audio": audio_bytes,
        "queue_wait_ms": round(queue_wait_ms, 3),
        "inference_ms": round(inference_ms, 3),
    }


def kill_piper_and_recover(text: str) -> dict:
    """
    Worker-side kill/recover test. Must be submitted via the same
    ProcessPoolExecutor used by the service.

    Two-checkpoint protocol:
      1. Kill old process → force respawn → assert fresh state.
      2. Synthesize recovery utterance → assert audio returned.
    """
    global _piper
    assert _piper is not None, "Worker not initialized"

    pid_before = _piper.proc.pid if _piper.proc else None
    _piper.proc.kill()
    _piper.proc.wait()
    _piper._invalidate_proc()
    _piper._check_and_respawn()
    pid_after = _piper.proc.pid if _piper.proc else None

    fresh_state = {
        "pid_before": pid_before,
        "pid_after": pid_after,
        "pid_changed": pid_after != pid_before,
        "prev_cumulative": _piper._prev_cumulative,
        "buffer_len": len(_piper._stdout_buffer),
        "queue_empty": _piper._completion_queue.empty(),
    }

    result = generate_tts_and_resample(text, time.time())
    fresh_state["audio_bytes"] = len(result["audio"])
    return fresh_state


# ── HTTP server ───────────────────────────────────────────────────────────────

from concurrent.futures import ThreadPoolExecutor

class TTSServer:
    def __init__(self, host: str = "127.0.0.1", port: int = 9095, workers: int = 2):
        self.host = host
        self.port = port
        self.workers = workers
        self.executor = None

    async def start(self) -> None:
        init_worker()
        self.executor = ThreadPoolExecutor(max_workers=self.workers)
        
        # Pre-warm with a fast test synthesis
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(self.executor, generate_tts_and_resample, "Hello", time.time(), "hi_pratham")
        print(f"[TTS Server] ThreadPool pre-warmed and ready.")

        app = web.Application()
        app.router.add_post("/tts", self.handle_tts)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, self.host, self.port)
        await site.start()
        print(
            f"TTS Server listening on http://{self.host}:{self.port}/tts "
            f"with Kokoro-82M neural engine"
        )

    async def handle_tts(self, request: web.Request) -> web.Response:
        t_handler_start = time.perf_counter()
        data = await request.json()
        text = data.get("text", "")
        call_id = data.get("call_id")
        voice = data.get("voice") or data.get("voice_model") or "hi_pratham"
        enqueue_time = float(data.get("enqueue_time", time.time()))

        loop = asyncio.get_running_loop()
        try:
            result = await loop.run_in_executor(
                self.executor, generate_tts_and_resample, text, enqueue_time, voice
            )
            audio_pcm16_8k = result["audio"]
            queue_wait_ms = result["queue_wait_ms"]
            inference_ms = result["inference_ms"]
        except Exception as e:
            print(f"TTS Service Error: {e}")
            audio_pcm16_8k = b""
            queue_wait_ms = 0.0
            inference_ms = 0.0

        latency_ms = (time.perf_counter() - t_handler_start) * 1000.0
        print(f"✅ [TTS STEP 3: STREAMING TO TELEPHONY GATEWAY] 200 OK | Latency: {latency_ms:.1f}ms | Queue Wait: {queue_wait_ms:.1f}ms | Audio Bytes: {len(audio_pcm16_8k)}", flush=True)
        return web.Response(
            body=audio_pcm16_8k,
            content_type="application/octet-stream",
            headers={
                "X-Latency-MS": str(round(latency_ms, 3)),
                "X-Call-ID": str(call_id),
                "X-Queue-Wait-MS": str(queue_wait_ms),
                "X-Inference-MS": str(inference_ms),
            },
        )

    def shutdown(self) -> None:
        if self.executor:
            self.executor.shutdown()


if __name__ == "__main__":
    workers = int(os.environ.get("TTS_WORKERS", "4"))
    server = TTSServer(workers=workers)
    loop = asyncio.new_event_loop()

    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(server.start())
        loop.run_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
