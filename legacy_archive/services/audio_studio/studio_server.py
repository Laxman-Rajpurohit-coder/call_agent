import os
import sys
import json
import time
import wave
import io
import asyncio
import numpy as np

ROOT_DIR = r"c:\daily_works\superfone_call"
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from scipy.signal import resample_poly
from aiohttp import web
from services.tts.kokoro_engine import KokoroTTSEngine

CONFIG_FILE = r"c:\daily_works\superfone_call\services\audio_studio\active_config.json"
DEFAULT_CONFIG = {
    "voice": "af_sarah",
    "speed": 1.0,
    "volume_gain_db": 0.0,
    "fade_in_ms": 4.0,
    "silence_padding_ms": 40.0,
    "barge_in_fade_ms": 40.0,
    "use_kokoro": True
}

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
            _pratham_piper = PersistentPiper(
                r"c:\daily_works\superfone_call\piper\piper\piper.exe",
                r"c:\daily_works\superfone_call\models\hi_IN-pratham-medium.onnx"
            )
            _pratham_piper.start()
        except Exception as ex:
            print(f"[Studio] Pratham Piper init warning: {ex}")
    return _pratham_piper

def _synthesize_sync(text: str, voice: str, speed: float, volume_gain_db: float, fade_in_ms: float) -> tuple[bytes, dict]:
    global _engine
    t0 = time.perf_counter()
    is_hindi = any(ord(c) >= 0x0900 and ord(c) <= 0x097F for c in text) or voice == "hi_pratham"

    # 1. Native Hindi Pratham Model
    if voice == "hi_pratham" or (is_hindi and voice != "af_sarah"):
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
        # 2. Kokoro-82M Neural Engine
        if not _engine or not _engine.kokoro:
            _engine = KokoroTTSEngine()
        lang_code = "hi" if is_hindi else "en-us"
        samples_24k, _ = _engine.kokoro.create(
            text,
            voice=voice,
            speed=speed,
            lang=lang_code
        )
        if samples_24k is None or len(samples_24k) == 0:
            raise ValueError("Kokoro returned empty audio samples")
        samples_8k = resample_poly(samples_24k, 1, 3)

    # 3. Volume Gain
    if volume_gain_db != 0.0:
        samples_8k = samples_8k * (10.0 ** (volume_gain_db / 20.0))

    # 4. Soft Attack Fade-In
    fade_len = int((fade_in_ms / 1000.0) * 8000)
    if fade_len > 0 and len(samples_8k) > fade_len:
        samples_8k[:fade_len] *= np.linspace(0.0, 1.0, fade_len)

    # 5. Clip to int16 PCM
    samples_int16 = np.clip(samples_8k * 32767.0, -32767.0, 32767.0).astype(np.int16)
    raw_pcm = samples_int16.tobytes()

    # 6. Format standard WAV container
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
        html_path = r"c:\daily_works\superfone_call\services\audio_studio\index.html"
        with open(html_path, "r", encoding="utf-8") as f:
            content = f.read()
        return web.Response(text=content, content_type="text/html")

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
            text = data.get("text", "Hello, welcome to Malisaini Samaj Seva Foundation.")
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
