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
import logging
from typing import Dict, Any, List
from aiohttp import web

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from path_c_hybrid_agent.stt_deepgram import transcribe_audio_chunk
from path_c_hybrid_agent.llm_groq import stream_llm_response
from path_c_hybrid_agent.tts_cartesia import synthesize_speech
from path_c_hybrid_agent.crm_postgres import init_db, handle_call_start, handle_call_end

logging.basicConfig(level=logging.INFO, format="%(asctime)s - [TwilioGateway] - %(message)s")
logger = logging.getLogger("TwilioGateway")

TWILIO_PORT = 9096
PUBLIC_DOMAIN = "overuse-clubbed-graffiti.ngrok-free.dev"
FRAME_SIZE_MULAW = 160 # 20ms at 8kHz mu-law mono
VAD_SILENCE_FRAMES = 25 # ~500ms silence threshold
VAD_RMS_THRESHOLD = 250


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
            {"role": "assistant", "content": "राम-राम सा! माली सैनी समाज सेवा फाउंडेशन में आपरो घणो-घणो स्वागत है। मैं आपकी काई सहायता कर सकूँ?"}
        ]
        self.pcm_rx_buffer = bytearray()
        self.has_speech = False
        self.silent_frames = 0
        self.is_speaking = False

    async def send_audio_mulaw(self, pcm_bytes: bytes):
        """Converts PCM audio to G.711 mu-law, encodes to Base64, and streams over Twilio WebSocket."""
        if not pcm_bytes or not self.ws:
            return
        self.is_speaking = True

        mulaw_data = audioop.lin2ulaw(pcm_bytes, 2)
        total_frames = (len(mulaw_data) + FRAME_SIZE_MULAW - 1) // FRAME_SIZE_MULAW

        t_start = time.perf_counter()
        for idx in range(total_frames):
            offset = idx * FRAME_SIZE_MULAW
            chunk = mulaw_data[offset:offset + FRAME_SIZE_MULAW]
            if not chunk:
                continue

            b64_payload = base64.b64encode(chunk).decode("ascii")
            media_msg = {
                "event": "media",
                "streamSid": self.stream_sid,
                "media": {"payload": b64_payload}
            }
            try:
                await self.ws.send_str(json.dumps(media_msg))
            except Exception as e:
                logger.warning("Twilio websocket send exception: %s", e)
                break

            target_time = t_start + (idx + 1) * 0.020
            sleep_needed = target_time - time.perf_counter()
            if sleep_needed > 0.001:
                await asyncio.sleep(sleep_needed)

        self.is_speaking = False

    async def send_initial_greeting(self):
        """Sends live greeting upon Twilio stream start in Marwadi."""
        greeting = "राम-राम सा! माली सैनी समाज सेवा फाउंडेशन में आपरो घणो-घणो स्वागत है। मैं आपकी काई सहायता कर सकूँ?"
        logger.info("[%s] Sending Live Initial Marwadi Greeting to Twilio...", self.stream_sid)
        pcm_out = await synthesize_speech(greeting)
        if pcm_out:
            await self.send_audio_mulaw(pcm_out)

    async def process_caller_utterance(self, pcm_bytes: bytes):
        """Executes Path C Pipeline: STT -> Groq LLM -> Cartesia TTS -> Twilio Stream."""
        if len(pcm_bytes) < 3200:
            return

        t0 = time.time()
        logger.info("[%s] Processing Twilio Utterance (%d bytes)...", self.stream_sid, len(pcm_bytes))

        # 1. Deepgram STT
        stt_res = await transcribe_audio_chunk(pcm_bytes)
        user_text = stt_res.get("text", "").strip()
        stt_time = round((time.time() - t0) * 1000, 1)

        if not user_text:
            logger.info("[%s] STT Empty or Silent. (STT Time: %.1fms)", self.stream_sid, stt_time)
            return

        logger.info("[%s] 🗣️ Twilio STT Output: '%s' (STT Time: %.1fms)", self.stream_sid, user_text, stt_time)
        self.conversation_history.append({"role": "user", "content": user_text})

        # 2. Groq LLM Stream -> Cartesia TTS Pipeline
        bot_response_text = ""
        full_buffer = ""

        async for token in stream_llm_response(user_text, self.conversation_history):
            bot_response_text += token
            full_buffer += token

        clean_text = full_buffer.strip()
        if clean_text:
            pcm_out = await synthesize_speech(clean_text)
            if pcm_out:
                await self.send_audio_mulaw(pcm_out)

        total_turn_ms = round((time.time() - t0) * 1000, 1)
        bot_response_text = bot_response_text.strip()
        logger.info("[%s] 🤖 Twilio LLM Response: '%s' (Total Latency: %.1fms)", self.stream_sid, bot_response_text, total_turn_ms)
        self.conversation_history.append({"role": "assistant", "content": bot_response_text})

    def close(self):
        duration = round(time.time() - self.start_time, 2)
        handle_call_end(self.call_sid, self.conversation_history, status="completed", duration_s=duration)
        logger.info("[%s] Twilio Session Finished: duration=%.2fs CRM Saved.", self.stream_sid, duration)


async def handle_voice_webhook(request):
    """HTTP POST/GET /voice Endpoint: Returns TwiML XML instructing Twilio to connect Media Stream."""
    host = request.headers.get("Host", PUBLIC_DOMAIN)
    scheme = "wss" if "ngrok" in host or request.scheme == "https" else "ws"
    ws_url = f"wss://{PUBLIC_DOMAIN}/media"

    twiml_response = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Connect>
        <Stream url="{ws_url}" />
    </Connect>
</Response>"""

    logger.info("📥 Incoming Twilio HTTP Voice Webhook from %s -> Returning TwiML Stream URL: %s", request.remote, ws_url)
    return web.Response(text=twiml_response, content_type="text/xml")


async def handle_media_websocket(request):
    """WebSocket /media Endpoint: Streams live audio between Twilio and Path C Marwadi Agent."""
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    logger.info("🚀 New Twilio Media Stream WebSocket Connection Established from %s", request.remote)
    
    session = None

    try:
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                try:
                    msg_data = json.loads(msg.data)
                    event_type = msg_data.get("event")

                    if event_type == "start":
                        start_obj = msg_data.get("start", {})
                        stream_sid = start_obj.get("streamSid", f"tw_stream_{int(time.time())}")
                        call_sid = start_obj.get("callSid", f"tw_call_{int(time.time())}")
                        custom_params = start_obj.get("customParameters", {})
                        caller = custom_params.get("caller", "+919811223344")

                        session = TwilioCallSession(stream_sid, call_sid, ws, caller)
                        logger.info("🚀 Twilio Stream Started: StreamSid=%s, CallSid=%s", stream_sid, call_sid)
                        
                        # Send initial Marwadi greeting
                        asyncio.create_task(session.send_initial_greeting())

                    elif event_type == "media" and session:
                        media_obj = msg_data.get("media", {})
                        b64_payload = media_obj.get("payload")
                        if b64_payload:
                            mulaw_bytes = base64.b64decode(b64_payload)
                            pcm_bytes = audioop.ulaw2lin(mulaw_bytes, 2)
                            session.pcm_rx_buffer.extend(pcm_bytes)
                            
                            rms = audioop.rms(pcm_bytes, 2)
                            if rms > VAD_RMS_THRESHOLD:
                                session.has_speech = True
                                session.silent_frames = 0
                            elif session.has_speech:
                                session.silent_frames += 1
                                if session.silent_frames >= VAD_SILENCE_FRAMES:
                                    speech_chunk = bytes(session.pcm_rx_buffer)
                                    session.pcm_rx_buffer = bytearray()
                                    session.has_speech = False
                                    session.silent_frames = 0
                                    asyncio.create_task(session.process_caller_utterance(speech_chunk))

                    elif event_type == "stop" and session:
                        logger.info("🛑 Twilio Stream Stopped: StreamSid=%s", session.stream_sid)
                        break

                except Exception as ex:
                    logger.error("Twilio message error: %s", ex)

            elif msg.type == web.WSMsgType.ERROR:
                logger.error("Twilio WebSocket connection error: %s", ws.exception())

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
    app.router.add_get('/', handle_voice_webhook)
    app.router.add_get('/media', handle_media_websocket)
    return app


async def main():
    init_db()
    app = create_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', TWILIO_PORT)
    await site.start()
    
    logger.info("=" * 80)
    logger.info("  🚀 LIVE TWILIO GATEWAY (HTTP + WEBSOCKET) READY ON PORT %d", TWILIO_PORT)
    logger.info("  PUBLIC DOMAIN : https://%s", PUBLIC_DOMAIN)
    logger.info("  TWILIO WEBHOOK : https://%s/voice", PUBLIC_DOMAIN)
    logger.info("  MEDIA STREAM   : wss://%s/media", PUBLIC_DOMAIN)
    logger.info("================================================================================")
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
