import os
import sys
import json
import time
import wave
import io
import asyncio
from pathlib import Path
import numpy as np
import urllib.request
import urllib.error

WORKSPACE_DIR = str(Path(__file__).resolve().parents[2])
LEGACY_DIR = r"c:\daily_works\superfone_call"
ROOT_DIR = WORKSPACE_DIR if os.path.exists(WORKSPACE_DIR) else LEGACY_DIR

if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

# Multi-path .env resolution (AGENTS.md Rule 4)
for env_candidate in (
    os.path.join(WORKSPACE_DIR, ".env"),
    os.path.join(LEGACY_DIR, ".env"),
    os.path.join(str(Path(__file__).parent), ".env"),
):
    if os.path.exists(env_candidate):
        try:
            with open(env_candidate, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and "=" in line and not line.startswith("#"):
                        k, v = line.split("=", 1)
                        k_clean = k.strip()
                        if k_clean not in os.environ:
                            os.environ[k_clean] = v.strip().strip('"').strip("'")
        except Exception:
            pass

from scipy.signal import resample_poly
from aiohttp import web
from services.tts.kokoro_engine import KokoroTTSEngine

CONFIG_FILE = os.path.join(ROOT_DIR, "services", "audio_studio", "active_config.json")
DEFAULT_CONFIG = {
    "voice": "af_sarah",
    "speed": 1.0,
    "volume_gain_db": 0.0,
    "fade_in_ms": 4.0,
    "silence_padding_ms": 40.0,
    "barge_in_fade_ms": 40.0,
    "use_kokoro": True
}

def log_debug(msg: str):
    print(f"[Studio Debug] {msg}")
    try:
        log_dir = os.path.join(ROOT_DIR, "scratch")
        os.makedirs(log_dir, exist_ok=True)
        with open(os.path.join(log_dir, "studio_debug.log"), "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except Exception:
        pass

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return {**DEFAULT_CONFIG, **json.load(f)}
        except Exception:
            pass
    return DEFAULT_CONFIG.copy()

def save_config(cfg):
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)

# Global engine instances
_engine = KokoroTTSEngine()
_pratham_piper = None

def get_pratham_piper():
    global _pratham_piper
    if _pratham_piper is None:
        try:
            from services.tts.worker import PersistentPiper
            piper_exe = os.path.join(ROOT_DIR, "piper", "piper", "piper.exe")
            piper_model = os.path.join(ROOT_DIR, "models", "hi_IN-pratham-medium.onnx")
            if not os.path.exists(piper_exe):
                piper_exe = r"c:\daily_works\superfone_call\piper\piper\piper.exe"
            if not os.path.exists(piper_model):
                piper_model = r"c:\daily_works\superfone_call\models\hi_IN-pratham-medium.onnx"
            _pratham_piper = PersistentPiper(piper_exe, piper_model)
            _pratham_piper.start()
        except Exception as ex:
            print(f"[Studio] Pratham Piper init warning: {ex}")
    return _pratham_piper

def _synthesize_sync(text: str, voice: str, speed: float, volume_gain_db: float, fade_in_ms: float) -> tuple[bytes, dict]:
    global _engine
    t0 = time.perf_counter()
    is_hindi = any(ord(c) >= 0x0900 and ord(c) <= 0x097F for c in text) or voice == "hi_pratham" or "hi_" in voice

    # 1. Deepgram Aura Cloud Direct Neural TTS
    if voice.startswith("deepgram_") or voice.startswith("aura_"):
        dg_key = os.environ.get("DEEPGRAM_API_KEY", "")
        log_debug(f"Deepgram Aura TTS voice={voice} | key_present={bool(dg_key)}")
        if dg_key:
            try:
                # Map model name
                model_name = "aura-asteria-en"
                if "luna" in voice:
                    model_name = "aura-luna-en"
                elif "stella" in voice:
                    model_name = "aura-stella-en"
                elif "zeus" in voice:
                    model_name = "aura-zeus-en"

                url = f"https://api.deepgram.com/v1/speak?model={model_name}&encoding=linear16&sample_rate=8000"
                headers = {
                    "Authorization": f"Token {dg_key}",
                    "Content-Type": "application/json"
                }
                payload = json.dumps({"text": text}).encode("utf-8")
                req = urllib.request.Request(url, data=payload, headers=headers)
                with urllib.request.urlopen(req, timeout=8.0) as resp:
                    raw_pcm = resp.read()
                    if len(raw_pcm) > 100:
                        samples_int16 = np.frombuffer(raw_pcm, dtype=np.int16)
                        wav_buf = io.BytesIO()
                        with wave.open(wav_buf, "wb") as wf:
                            wf.setnchannels(1)
                            wf.setsampwidth(2)
                            wf.setframerate(8000)
                            wf.writeframes(raw_pcm)
                        wav_bytes = wav_buf.getvalue()
                        dur_s = len(samples_int16) / 8000.0
                        elapsed_ms = (time.perf_counter() - t0) * 1000.0
                        rtf = (elapsed_ms / 1000.0) / dur_s if dur_s > 0 else 0.0
                        rms = float(np.sqrt(np.mean(samples_int16.astype(np.float64)**2))) if len(samples_int16) > 0 else 0.0
                        rms_dbfs = 20.0 * np.log10(rms / 32768.0) if rms > 0 else -100.0
                        peak = int(np.max(np.abs(samples_int16))) if len(samples_int16) > 0 else 0
                        log_debug(f"DEEPGRAM AURA TTS SUCCESS: {len(raw_pcm)} bytes in {elapsed_ms:.1f}ms")
                        return wav_bytes, {
                            "dur_s": dur_s,
                            "elapsed_ms": elapsed_ms,
                            "rtf": rtf,
                            "rms_dbfs": rms_dbfs,
                            "peak": peak
                        }
            except Exception as ex:
                log_debug(f"DEEPGRAM AURA ERROR: {ex}. Falling back to Kokoro.")

    # 2. Cartesia Sonic Cloud Primary API
    if voice.startswith("cartesia_"):
        cartesia_key = os.environ.get("CARTESIA_API_KEY", "")
        log_debug(f"Cartesia Cloud TTS voice={voice} | key_present={bool(cartesia_key)}")
        if cartesia_key:
            try:
                url = "https://api.cartesia.ai/tts/bytes"
                headers = {
                    "X-API-Key": cartesia_key,
                    "Cartesia-Version": "2024-06-10",
                    "Content-Type": "application/json"
                }
                lang = "hi" if is_hindi or "hi" in voice or "hinglish" in voice else "en"
                payload = json.dumps({
                    "model_id": "sonic-preview",
                    "transcript": text,
                    "voice": {"mode": "id", "id": "14008c51-fbf4-418e-ae23-9316a03dcfa2"},
                    "output_format": {"container": "raw", "encoding": "pcm_s16le", "sample_rate": 8000},
                    "language": lang
                }).encode("utf-8")
                req = urllib.request.Request(url, data=payload, headers=headers)
                with urllib.request.urlopen(req, timeout=8.0) as resp:
                    raw_pcm = resp.read()
                    if len(raw_pcm) > 100:
                        samples_int16 = np.frombuffer(raw_pcm, dtype=np.int16)
                        wav_buf = io.BytesIO()
                        with wave.open(wav_buf, "wb") as wf:
                            wf.setnchannels(1)
                            wf.setsampwidth(2)
                            wf.setframerate(8000)
                            wf.writeframes(raw_pcm)
                        wav_bytes = wav_buf.getvalue()
                        dur_s = len(samples_int16) / 8000.0
                        elapsed_ms = (time.perf_counter() - t0) * 1000.0
                        rtf = (elapsed_ms / 1000.0) / dur_s if dur_s > 0 else 0.0
                        rms = float(np.sqrt(np.mean(samples_int16.astype(np.float64)**2))) if len(samples_int16) > 0 else 0.0
                        rms_dbfs = 20.0 * np.log10(rms / 32768.0) if rms > 0 else -100.0
                        peak = int(np.max(np.abs(samples_int16))) if len(samples_int16) > 0 else 0
                        log_debug(f"CARTESIA CLOUD TTS SUCCESS: {len(raw_pcm)} bytes in {elapsed_ms:.1f}ms")
                        return wav_bytes, {
                            "dur_s": dur_s,
                            "elapsed_ms": elapsed_ms,
                            "rtf": rtf,
                            "rms_dbfs": rms_dbfs,
                            "peak": peak
                        }
            except Exception as ex:
                log_debug(f"CARTESIA CLOUD ERROR: {ex}. Falling back to Kokoro.")

    # 3. Native Hindi Pratham / Aditi Models
    if voice in ("hi_pratham", "hi_aditi"):
        piper = get_pratham_piper()
        if piper:
            pcm_22k = piper.synthesize(text)
            if not pcm_22k:
                raise ValueError("Piper Hindi returned empty audio")
            samples = np.frombuffer(pcm_22k, dtype=np.int16).astype(np.float32)
            samples_8k = resample_poly(samples, 160, 441)
        else:
            raise RuntimeError("Hindi Pratham model not loaded")
    else:
        # 4. Kokoro-82M Neural Engine (with Cloud Neural fallback)
        samples_8k = None
        if _engine and _engine.kokoro:
            try:
                lang_code = "hi" if is_hindi else "en-us"
                kokoro_voice = voice if voice in ("af_sarah", "af_bella", "am_adam", "am_michael", "bf_emma", "bm_george") else "af_sarah"
                samples_24k, _ = _engine.kokoro.create(
                    text,
                    voice=kokoro_voice,
                    speed=speed,
                    lang=lang_code
                )
                if samples_24k is not None and len(samples_24k) > 0:
                    samples_8k = resample_poly(samples_24k, 1, 3)
            except Exception as e:
                log_debug(f"Kokoro synth error: {e}")

        # If local Kokoro was uninitialized or failed, seamlessly fallback to Deepgram Aura
        if samples_8k is None:
            dg_key = os.environ.get("DEEPGRAM_API_KEY", "")
            if dg_key:
                try:
                    url = "https://api.deepgram.com/v1/speak?model=aura-asteria-en&encoding=linear16&sample_rate=8000"
                    headers = {"Authorization": f"Token {dg_key}", "Content-Type": "application/json"}
                    payload = json.dumps({"text": text}).encode("utf-8")
                    req = urllib.request.Request(url, data=payload, headers=headers)
                    with urllib.request.urlopen(req, timeout=8.0) as resp:
                        raw_pcm = resp.read()
                        if len(raw_pcm) > 100:
                            samples_int16 = np.frombuffer(raw_pcm, dtype=np.int16)
                            samples_8k = samples_int16.astype(np.float32) / 32768.0
                except Exception as ex:
                    log_debug(f"Deepgram fallback error: {ex}")

        if samples_8k is None:
            raise RuntimeError("All TTS engines unavailable")

    # 5. Volume Gain
    if volume_gain_db != 0.0:
        samples_8k = samples_8k * (10.0 ** (volume_gain_db / 20.0))

    # 6. Soft Attack Fade-In
    fade_len = int((fade_in_ms / 1000.0) * 8000)
    if fade_len > 0 and len(samples_8k) > fade_len:
        samples_8k[:fade_len] *= np.linspace(0.0, 1.0, fade_len)

    # 7. Clip to int16 PCM
    samples_int16 = np.clip(samples_8k * 32767.0, -32767.0, 32767.0).astype(np.int16)
    raw_pcm = samples_int16.tobytes()

    # 8. Format standard WAV container
    wav_buf = io.BytesIO()
    with wave.open(wav_buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(8000)
        wf.writeframes(raw_pcm)
    wav_bytes = wav_buf.getvalue()

    dur_s = len(samples_int16) / 8000.0
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    rtf = (elapsed_ms / 1000.0) / dur_s if dur_s > 0 else 0.0
    rms = float(np.sqrt(np.mean(samples_int16.astype(np.float64)**2))) if len(samples_int16) > 0 else 0.0
    rms_dbfs = 20.0 * np.log10(rms / 32768.0) if rms > 0 else -100.0
    peak = int(np.max(np.abs(samples_int16))) if len(samples_int16) > 0 else 0

    metrics = {
        "dur_s": dur_s,
        "elapsed_ms": elapsed_ms,
        "rtf": rtf,
        "rms_dbfs": rms_dbfs,
        "peak": peak
    }
    return wav_bytes, metrics

class AudioStudioServer:
    def __init__(self, host: str = "0.0.0.0", port: int = 9096):
        self.host = host
        self.port = port

    async def handle_index(self, request: web.Request) -> web.Response:
        html_path = os.path.join(ROOT_DIR, "services", "audio_studio", "index.html")
        if not os.path.exists(html_path):
            html_path = r"c:\daily_works\superfone_call\services\audio_studio\index.html"
        if os.path.exists(html_path):
            with open(html_path, "r", encoding="utf-8") as f:
                content = f.read()
            return web.Response(text=content, content_type="text/html")
        return web.Response(text="<h1>Audio Studio Server Ready</h1>", content_type="text/html")

    async def handle_get_config(self, request: web.Request) -> web.Response:
        return web.json_response(load_config())

    async def handle_save_config(self, request: web.Request) -> web.Response:
        data = await request.json()
        cfg = load_config()
        cfg.update(data)
        save_config(cfg)
        return web.json_response({"status": "saved", "config": cfg})

    async def handle_synthesize(self, request: web.Request) -> web.Response:
        try:
            data = await request.json()
            text = data.get("text", "Hello, welcome to Superfone AI Voice Operations Platform.")
            voice = data.get("voice", "af_sarah")
            speed = float(data.get("speed", 1.0))
            volume_gain_db = float(data.get("volume_gain_db", 0.0))
            fade_in_ms = float(data.get("fade_in_ms", 4.0))

            loop = asyncio.get_running_loop()
            wav_bytes, metrics = await loop.run_in_executor(
                None, _synthesize_sync, text, voice, speed, volume_gain_db, fade_in_ms
            )

            headers = {
                "Content-Type": "audio/wav",
                "X-Duration-Sec": f"{metrics['dur_s']:.2f}",
                "X-Latency-MS": f"{metrics['elapsed_ms']:.1f}",
                "X-RTF": f"{metrics['rtf']:.3f}",
                "X-RMS-DBFS": f"{metrics['rms_dbfs']:.1f}",
                "X-Peak": str(metrics["peak"]),
                "Access-Control-Expose-Headers": "X-Duration-Sec, X-Latency-MS, X-RTF, X-RMS-DBFS, X-Peak"
            }
            return web.Response(body=wav_bytes, headers=headers)
        except Exception as ex:
            import traceback
            traceback.print_exc()
            return web.json_response({"error": str(ex)}, status=500)

    async def start(self):
        app = web.Application()
        app.router.add_get("/", self.handle_index)
        app.router.add_get("/api/config", self.handle_get_config)
        app.router.add_post("/api/config", self.handle_save_config)
        app.router.add_post("/api/synthesize", self.handle_synthesize)

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, self.host, self.port)
        await site.start()
        print(f"============================================================")
        print(f"  AUDIO STUDIO PARAMETER CONTROL UI RUNNING")
        print(f"  Open in Browser: http://localhost:{self.port}")
        print(f"============================================================")

if __name__ == "__main__":
    server = AudioStudioServer(port=9096)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(server.start())
        loop.run_forever()
    except KeyboardInterrupt:
        pass
