"""
Path C Live Twilio Media Stream Gateway (Port 9096 HTTP & WebSocket)
Public Ngrok Domain: overuse-clubbed-graffiti.ngrok-free.dev
Handles Twilio HTTP Voice Webhook (/voice) & WebSocket Media Stream (/media).
"""

import os
import sys
import time
import json
import base64
import asyncio
import audioop
import wave
import logging
from typing import Dict, Any, List, Optional
from aiohttp import web

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from path_c_hybrid_agent.stt_deepgram import transcribe_audio_chunk
from path_c_hybrid_agent.llm_groq import stream_llm_response, clean_reasoning_tokens, normalize_phonetics_for_tts
from path_c_hybrid_agent.tts_cartesia import synthesize_speech
from path_c_hybrid_agent.crm_postgres import init_db, handle_call_start, handle_call_end

logging.basicConfig(level=logging.INFO, format="%(asctime)s - [TwilioGateway] - %(message)s")
logger = logging.getLogger("TwilioGateway")

TWILIO_PORT = 9096
PUBLIC_DOMAIN = "drool-envoy-sandy.ngrok-free.dev"


FRAME_SIZE_MULAW = 160 # 20ms at 8kHz mu-law mono
VAD_SILENCE_FRAMES = 17 # ~340ms silence threshold (< 350ms rule)
VAD_RMS_THRESHOLD = 60 # Sensitive threshold for telephony audio


INITIAL_GREETING_TEXT = "राम-राम सा! माली सैनी समाज सेवा फाउंडेशन में आपरो घणो-घणो स्वागत है। मैं आपकी काई सहायता कर सकूँ?"
PRECACHED_GREETING_PCM: Optional[bytes] = None

import numpy as np

class TwilioCallSession:
    def __init__(self, stream_sid: str, call_sid: str, ws, caller_number: str = "+919811223344"):
        self.stream_sid = stream_sid
        self.call_sid = call_sid
        self.ws = ws
        self.caller_number = caller_number
        self.start_time = time.time()
        
        # CRM Lifecycle Init
        self.crm_info = handle_call_start(self.call_sid, self.caller_number, "+918000000700", direction="inbound", provider="twilio")
        self.conversation_history: List[Dict[str, str]] = [
            {"role": "assistant", "content": INITIAL_GREETING_TEXT}
        ]
        self.pcm_rx_buffer = bytearray()
        self.has_speech = False
        self.silent_frames = 0
        self.is_speaking = False
        self.is_active = True
        self.is_pcm16 = False
        self.frame_count = 0
        
        # Free Local Call Recording (Native 8kHz Telephony WAV Header per Rule 4)
        rec_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "recordings")
        os.makedirs(rec_dir, exist_ok=True)
        self.rec_filename = os.path.join(rec_dir, f"{self.call_sid}.wav")
        try:
            self.wav_file = wave.open(self.rec_filename, 'wb')
            self.wav_file.setnchannels(1)
            self.wav_file.setsampwidth(2)
            self.wav_file.setframerate(8000)
            logger.info("[%s] 🎙️ Free Local Call Recording Started: %s", self.stream_sid, self.rec_filename)
        except Exception as ex:
            logger.warning("[%s] Could not open wave recording file: %s", self.stream_sid, ex)
            self.wav_file = None

        self.keepalive_task = asyncio.create_task(self.silence_keepalive_loop())

    async def send_mulaw_frame(self, chunk: bytes):
        """Sends audio frame formatted as Twilio/Exotel JSON media event."""
        if not self.ws or self.ws.closed:
            return
        b64_payload = base64.b64encode(chunk).decode('ascii')
        media_dict = {
            "event": "media",
            "stream_sid": self.stream_sid,
            "streamSid": self.stream_sid,
            "media": {
                "payload": b64_payload,
                "track": "outbound",
                "stream_sid": self.stream_sid,
                "streamSid": self.stream_sid
            }
        }

        media_msg = json.dumps(media_dict)
        try:
            await self.ws.send_str(media_msg)
        except Exception:
            try:
                await self.ws.send_bytes(chunk)
            except Exception:
                pass

    async def silence_keepalive_loop(self):
        """Maintains active session loop with zero microphone audio suppression."""
        while self.is_active and self.ws and not self.ws.closed:
            await asyncio.sleep(1.0)

    async def send_audio_mulaw(self, pcm_bytes: bytes):
        """Streams 8kHz audio over WebSocket with auto-detection for 16-bit PCM (Exotel) vs G.711 mu-law (Twilio)."""
        if not pcm_bytes or not self.ws or self.ws.closed:
            return
        self.is_speaking = True

        # 1. Peak Gain Normalization to -2dBFS for loud, crisp telephony playback
        try:
            samples = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32)
            max_val = np.max(np.abs(samples))
            if max_val > 50 and max_val < 20000:
                scale = 25000.0 / max_val
                samples_norm = np.clip(samples * scale, -32767, 32767).astype(np.int16)
                pcm_bytes = samples_norm.tobytes()
        except Exception:
            pass

        # 2. Record outgoing AI speech to local WAV file
        if getattr(self, 'wav_file', None):
            try:
                self.wav_file.writeframes(pcm_bytes)
            except Exception:
                pass

        # 3. Format selection: Exotel (16-bit PCM 128kbps -> 320 bytes/20ms) vs Twilio (8-bit mu-law 64kbps -> 160 bytes/20ms)
        if self.is_pcm16:
            frame_size = 320
            out_data = pcm_bytes
        else:
            frame_size = 160
            out_data = audioop.lin2ulaw(pcm_bytes, 2)

        total_frames = (len(out_data) + frame_size - 1) // frame_size
        t_start = time.perf_counter()
        for idx in range(total_frames):
            if self.ws.closed:
                break
            offset = idx * frame_size
            chunk = out_data[offset:offset + frame_size]
            if not chunk:
                continue

            await self.send_mulaw_frame(chunk)

            target_time = t_start + (idx + 1) * 0.020
            sleep_needed = target_time - time.perf_counter()
            if sleep_needed > 0.001:
                await asyncio.sleep(sleep_needed)

        self.is_speaking = False


    async def send_initial_greeting(self):
        """Sends live greeting upon Twilio/Exotel stream start in Marwadi."""
        global PRECACHED_GREETING_PCM
        logger.info("[%s] Sending Live Initial Marwadi Greeting to CPaaS...", self.stream_sid)
        if PRECACHED_GREETING_PCM is None:
            PRECACHED_GREETING_PCM = await synthesize_speech(INITIAL_GREETING_TEXT)
        if PRECACHED_GREETING_PCM and not self.ws.closed:
            await self.send_audio_mulaw(PRECACHED_GREETING_PCM)

    async def process_caller_utterance(self, pcm_bytes: bytes):
        """Executes Path C Pipeline: STT -> Groq LLM -> Cartesia TTS -> Twilio Stream."""
        if len(pcm_bytes) < 1600:
            return

        # Record incoming customer speech to local WAV file
        if getattr(self, 'wav_file', None):
            try:
                self.wav_file.writeframes(pcm_bytes)
            except Exception:
                pass

        t0 = time.time()
        logger.info("[%s] 🎙️ Processing Telephony Utterance (%d bytes)...", self.stream_sid, len(pcm_bytes))

        # 1. Groq / Deepgram Dual Cloud STT
        stt_res = await transcribe_audio_chunk(pcm_bytes)
        user_text = stt_res.get("text", "").strip()
        stt_provider = stt_res.get("provider", "none")
        stt_time = round((time.time() - t0) * 1000, 1)

        if not user_text:
            logger.info("[%s] ⚠️ STT Empty or Silent. (STT Time: %.1fms, Provider: %s)", self.stream_sid, stt_time, stt_provider)
            return

        logger.info("[%s] 🗣️ User Spoke (%s, %.1fms): '%s'", self.stream_sid, stt_provider, stt_time, user_text)
        self.conversation_history.append({"role": "user", "content": user_text})

        # 2. Groq LLM Stream -> Cartesia TTS Pipeline
        bot_response_text = ""
        full_buffer = ""

        async for token in stream_llm_response(self.conversation_history, max_tokens=35):
            bot_response_text += token
            full_buffer += token

        clean_text = clean_reasoning_tokens(normalize_phonetics_for_tts(full_buffer.strip()))
        if clean_text:
            logger.info("[%s] 🤖 AI Response: '%s'", self.stream_sid, clean_text)
            pcm_out = await synthesize_speech(clean_text)
            if pcm_out:
                await self.send_audio_mulaw(pcm_out)

        total_turn_ms = round((time.time() - t0) * 1000, 1)
        logger.info("[%s] ✅ Turn Completed in %.1fms", self.stream_sid, total_turn_ms)
        if clean_text:
            self.conversation_history.append({"role": "assistant", "content": clean_text})

    def close(self):
        self.is_active = False
        if hasattr(self, 'keepalive_task') and self.keepalive_task:
            self.keepalive_task.cancel()
        if getattr(self, 'wav_file', None):
            try:
                self.wav_file.close()
                logger.info("[%s] 🎙️ Free Local Call Recording Saved: %s", self.stream_sid, self.rec_filename)
            except Exception:
                pass
        duration = round(time.time() - self.start_time, 2)
        handle_call_end(self.call_sid, self.conversation_history, status="completed", duration_s=duration)
        logger.info("[%s] Telephony Session Finished: duration=%.2fs CRM Saved.", self.stream_sid, duration)



async def handle_voice_webhook(request):
    """HTTP POST/GET /voice & /api/telephony/webhook Endpoint: Returns TwiML XML or upgrades to WebSocket if requested."""
    if request.headers.get("Upgrade", "").lower() == "websocket" or "sec-websocket-key" in request.headers:
        logger.info("⚡ Incoming WebSocket Upgrade on Webhook Route from %s -> Forwarding to WebSocket Handler", request.remote)
        return await handle_media_websocket(request)

    host = request.headers.get("Host", PUBLIC_DOMAIN)
    scheme = "wss" if "ngrok" in host or request.scheme == "https" else "ws"
    ws_url = f"{scheme}://{host}/media-stream"

    twiml_response = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Connect>
        <Stream url="{ws_url}" />
    </Connect>
</Response>"""

    logger.info("📥 Incoming CPaaS HTTP Voice Webhook from %s (Host: %s) -> Returning TwiML Stream URL: %s", request.remote, host, ws_url)
    return web.Response(text=twiml_response, content_type="text/xml")



async def handle_media_websocket(request):
    """WebSocket Endpoint: Streams live audio between Exotel/Twilio and Voice Agent."""
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    logger.info("🚀 New Telephony Media Stream WebSocket Connection Established from %s", request.remote)
    
    stream_sid = f"ex_stream_{int(time.time())}"
    call_sid = f"ex_call_{int(time.time())}"
    session = TwilioCallSession(stream_sid, call_sid, ws, "+918830718466")
    logger.info("🚀 Telephony Call Session Auto-Started: StreamSid=%s", stream_sid)

    try:
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                try:
                    msg_data = json.loads(msg.data)
                    event_type = msg_data.get("event")

                    if event_type == "start":
                        logger.info("🚀 Received Raw Start Event Data: %s", msg.data)
                        start_obj = msg_data.get("start", {})
                        actual_sid = (
                            start_obj.get("streamSid") or 
                            start_obj.get("stream_sid") or 
                            start_obj.get("sid") or 
                            msg_data.get("streamSid") or 
                            msg_data.get("stream_sid") or 
                            msg_data.get("sid")
                        )
                        if actual_sid:
                            session.stream_sid = actual_sid
                        
                        media_format = start_obj.get("media_format", {})
                        sample_rate = int(media_format.get("sample_rate", 8000))
                        bit_rate = str(media_format.get("bit_rate", ""))
                        encoding = str(media_format.get("encoding", ""))
                        session.is_pcm16 = "128" in bit_rate or "pcm" in encoding.lower() or "linear" in encoding.lower() or "l16" in encoding.lower() or encoding.lower() == "base64"
                        logger.info("🚀 Media Format Detected: SampleRate=%d, BitRate=%s, Encoding=%s -> is_pcm16=%s", sample_rate, bit_rate, encoding, session.is_pcm16)

                        caller_num = start_obj.get("from") or start_obj.get("caller") or "+918830718466"
                        session.caller_number = caller_num

                        logger.info("🚀 Received Start Event: StreamSid=%s -> Triggering Live Greeting", session.stream_sid)
                        asyncio.create_task(session.send_initial_greeting())

                    elif event_type == "media":
                        media_obj = msg_data.get("media", {})
                        b64_payload = (
                            (media_obj.get("payload") if isinstance(media_obj, dict) else None) or
                            msg_data.get("payload") or
                            msg_data.get("chunk")
                        )
                        if b64_payload:
                            raw_bytes = base64.b64decode(b64_payload)
                            if len(raw_bytes) >= 320 or session.is_pcm16:
                                session.is_pcm16 = True
                                pcm_bytes = raw_bytes
                            else:
                                pcm_bytes = audioop.ulaw2lin(raw_bytes, 2)
                                
                            session.pcm_rx_buffer.extend(pcm_bytes)
                            
                            rms = audioop.rms(pcm_bytes, 2)
                            session.frame_count += 1
                            if session.frame_count <= 3 or session.frame_count % 100 == 0:
                                logger.info("[%s] 📊 Audio Frame #%d: len=%d bytes, RMS=%d (is_pcm16=%s)", session.stream_sid, session.frame_count, len(pcm_bytes), rms, session.is_pcm16)

                            if rms > VAD_RMS_THRESHOLD:
                                if not session.has_speech:
                                    logger.info("[%s] 🎙️ Speech Detected! (RMS=%d > %d)", session.stream_sid, rms, VAD_RMS_THRESHOLD)
                                session.has_speech = True
                                session.silent_frames = 0
                            elif session.has_speech:
                                session.silent_frames += 1
                                if session.silent_frames >= VAD_SILENCE_FRAMES:
                                    speech_chunk = bytes(session.pcm_rx_buffer)
                                    session.pcm_rx_buffer = bytearray()
                                    session.has_speech = False
                                    session.silent_frames = 0
                                    logger.info("[%s] 🗣️ User Utterance Completed (%d bytes audio) -> Processing STT & LLM", session.stream_sid, len(speech_chunk))
                                    asyncio.create_task(session.process_caller_utterance(speech_chunk))

                    elif event_type == "stop":
                        logger.info("ℹ️ Exotel sent stop event (ignoring break to keep stream connection active): StreamSid=%s", session.stream_sid)

                except Exception as ex:
                    logger.error("Telephony text message error: %s", ex)

            elif msg.type == web.WSMsgType.BINARY:
                try:
                    raw_bytes = msg.data
                    if len(raw_bytes) >= 320 or session.is_pcm16:
                        session.is_pcm16 = True
                        pcm_bytes = raw_bytes
                    else:
                        pcm_bytes = audioop.ulaw2lin(raw_bytes, 2)

                    session.pcm_rx_buffer.extend(pcm_bytes)
                    
                    rms = audioop.rms(pcm_bytes, 2)
                    session.frame_count += 1
                    if session.frame_count <= 3 or session.frame_count % 100 == 0:
                        logger.info("[%s] 📊 Binary Frame #%d: len=%d bytes, RMS=%d (is_pcm16=%s)", session.stream_sid, session.frame_count, len(pcm_bytes), rms, session.is_pcm16)

                    if rms > VAD_RMS_THRESHOLD:
                        if not session.has_speech:
                            logger.info("[%s] 🎙️ Speech Detected! (RMS=%d > %d)", session.stream_sid, rms, VAD_RMS_THRESHOLD)
                        session.has_speech = True
                        session.silent_frames = 0
                    elif session.has_speech:
                        session.silent_frames += 1
                        if session.silent_frames >= VAD_SILENCE_FRAMES:
                            speech_chunk = bytes(session.pcm_rx_buffer)
                            session.pcm_rx_buffer = bytearray()
                            session.has_speech = False
                            session.silent_frames = 0
                            logger.info("[%s] 🗣️ User Utterance Completed (%d bytes audio) -> Processing STT & LLM", session.stream_sid, len(speech_chunk))
                            asyncio.create_task(session.process_caller_utterance(speech_chunk))
                except Exception as ex:
                    logger.error("Telephony binary frame error: %s", ex)

            elif msg.type in (web.WSMsgType.ERROR, web.WSMsgType.CLOSED, web.WSMsgType.CLOSING):
                logger.info("Telephony WebSocket closing/closed.")
                break

    finally:
        if session:
            session.close()

    return ws



def create_app():
    app = web.Application()
    app.router.add_get('/voice', handle_voice_webhook)
    app.router.add_post('/voice', handle_voice_webhook)
    app.router.add_get('/twiml', handle_voice_webhook)
    app.router.add_post('/twiml', handle_voice_webhook)
    app.router.add_post('/api/telephony/webhook', handle_voice_webhook)
    app.router.add_get('/api/telephony/webhook', handle_media_websocket)
    app.router.add_get('/', handle_voice_webhook)
    app.router.add_get('/media', handle_media_websocket)
    app.router.add_get('/media-stream', handle_media_websocket)
    return app




if __name__ == "__main__":
    init_db()
    logger.info("⚡ Pre-synthesizing initial greeting for 0ms call setup latency...")
    PRECACHED_GREETING_PCM = asyncio.run(synthesize_speech(INITIAL_GREETING_TEXT))
    logger.info("✅ Initial greeting pre-rendered (%d bytes PCM audio pool ready).", len(PRECACHED_GREETING_PCM) if PRECACHED_GREETING_PCM else 0)

    logger.info("=" * 80)
    logger.info("  🚀 LIVE TWILIO GATEWAY (HTTP + WEBSOCKET) READY ON PORT %d", TWILIO_PORT)
    logger.info("  PUBLIC DOMAIN : https://%s", PUBLIC_DOMAIN)
    logger.info("  TWILIO WEBHOOK : https://%s/voice", PUBLIC_DOMAIN)
    logger.info("  MEDIA STREAM   : wss://%s/media", PUBLIC_DOMAIN)
    logger.info("================================================================================")
    web.run_app(create_app(), host="0.0.0.0", port=TWILIO_PORT)
