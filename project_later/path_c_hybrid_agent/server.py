"""
Path C Managed Cloud Hybrid AudioSocket Gateway Server
Receives 20ms/320B PCM frames over AudioSocket TCP (Port 9092), streams STT/LLM/TTS via Cloud APIs,
and persists calls to PostgreSQL 18 CRM.
"""

import os
import sys
import time
import json
import uuid
import asyncio
import struct
import logging

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from path_c_hybrid_agent.stt_deepgram import transcribe_audio_chunk
from path_c_hybrid_agent.llm_groq import stream_llm_response
from path_c_hybrid_agent.tts_cartesia import synthesize_speech
from path_c_hybrid_agent.crm_postgres import init_db, handle_call_start, handle_call_end

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("PathCHybridGateway")

GATEWAY_PORT = 9092

async def handle_connection(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    peer = writer.get_extra_info('peername')
    logger.info("[Path C Gateway] New AudioSocket call connected from %s", peer)

    # 1. Read AudioSocket UUID Header
    hdr = await reader.readexactly(3)
    p_type, p_len = struct.unpack('!BH', hdr)

    if p_type == 0x01:
        raw_uuid = await reader.readexactly(p_len)
        call_id = str(uuid.UUID(bytes=raw_uuid))
    else:
        call_id = str(uuid.uuid4())
        if p_len > 0:
            await reader.readexactly(p_len)

    logger.info("[Path C Gateway] Call Session Started: call_id=%s", call_id)

    # Trigger CRM Start
    caller_phone = str(peer[0]) if (peer and not str(peer[0]).startswith("127.")) else "+919811223344"
    crm_data = handle_call_start(call_id, caller_phone, "+918000000700", direction="inbound", provider="plivo")

    conversation_history = [
        {"role": "assistant", "content": "Namaste! Mali Saini Samaj Seva Foundation mein aapka swagat hai."}
    ]

    audio_buffer = bytearray()
    start_time = time.time()

    try:
        while True:
            try:
                hdr = await asyncio.wait_for(reader.readexactly(3), timeout=6.0)
                p_type, p_len = struct.unpack('!BH', hdr)
                payload = await reader.readexactly(p_len)
                if p_type == 0x10:
                    audio_buffer.extend(payload)
                elif p_type == 0x00:
                    break
            except asyncio.TimeoutError:
                break
            except Exception:
                break

        # Process STT -> LLM -> TTS pipeline
        if len(audio_buffer) > 3200: # > 200ms audio
            logger.info("[Path C Gateway] Processing STT for call_id=%s (audio_bytes=%d)", call_id, len(audio_buffer))
            stt_result = await transcribe_audio_chunk(bytes(audio_buffer))
            user_text = stt_result.get("text", "")

            if user_text:
                logger.info("[Path C Gateway] STT Text: '%s' (Provider: %s)", user_text, stt_result.get("provider"))
                conversation_history.append({"role": "user", "content": user_text})

                # Stream LLM Response
                bot_text = ""
                async for chunk in stream_llm_response(user_text, conversation_history):
                    bot_text += chunk

                bot_text = bot_text.strip()
                logger.info("[Path C Gateway] LLM Full Response: '%s'", bot_text)
                conversation_history.append({"role": "assistant", "content": bot_text})

                # Synthesize TTS
                pcm_out = await synthesize_speech(bot_text)
                if pcm_out:
                    FRAME = 320
                    for i in range(0, len(pcm_out), FRAME):
                        fr = pcm_out[i:i+FRAME]
                        if len(fr) < FRAME:
                            fr = fr.ljust(FRAME, b"\x00")
                        writer.write(struct.pack("!BH", 0x10, FRAME) + fr)
                        await asyncio.sleep(0.019)
                    await writer.drain()

    except Exception as err:
        logger.error("[Path C Gateway] Connection error: %s", err)
    finally:
        duration = round(time.time() - start_time, 2)
        handle_call_end(call_id, conversation_history, status="completed", duration_s=duration)
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        logger.info("[Path C Gateway] Call Session Finished: call_id=%s duration=%.2fs", call_id, duration)


async def main():
    init_db()
    server = await asyncio.start_server(handle_connection, '0.0.0.0', GATEWAY_PORT)
    addr = server.sockets[0].getsockname()
    logger.info("================================================================================")
    logger.info("  PATH C MANAGED CLOUD HYBRID AUDIOSOCKET GATEWAY LISTENING ON %s", addr)
    logger.info("================================================================================")
    async with server:
        await server.serve_forever()

if __name__ == "__main__":
    asyncio.run(main())
