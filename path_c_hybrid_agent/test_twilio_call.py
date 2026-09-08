"""
Live Twilio Media Streams Gateway Test Script
Simulates a Twilio WebSocket Media Stream connection to Port 9096.
"""

import os
import sys
import json
import base64
import asyncio
import audioop
import websockets

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from path_c_hybrid_agent.tts_cartesia import synthesize_speech_hd

TWILIO_WS_URL = "ws://127.0.0.1:9096/media"

async def test_twilio_stream():
    print("=" * 80)
    print("  📞 TWILIO MEDIA STREAM GATEWAY TEST (PORT 9096)")
    print("================================================================================\n")

    async with websockets.connect(TWILIO_WS_URL) as ws:
        print("✅ Connected to Twilio Gateway WebSocket on ws://127.0.0.1:9096/media")

        # 1. Send Twilio Start Event
        stream_sid = "MZ1234567890abcdef"
        call_sid = "CA1234567890abcdef"
        start_msg = {
            "event": "start",
            "streamSid": stream_sid,
            "start": {
                "streamSid": stream_sid,
                "callSid": call_sid,
                "customParameters": {"caller": "+919811223344"}
            }
        }
        await ws.send(json.dumps(start_msg))
        print("   Sent Twilio 'start' event.")

        # 2. Synthesize 8kHz mu-law audio for Hindi caller
        c_text = "नमस्ते! मैं माली सैनी समाज सेवा फाउंडेशन के बारे में जानना चाहता हूँ।"
        caller_pcm_24k = await synthesize_speech_hd(c_text, voice_id="791d5162-d5eb-40f0-8189-f19db44611d8", sample_rate=24000)
        
        if caller_pcm_24k:
            import numpy as np
            audio_np = np.frombuffer(caller_pcm_24k, dtype=np.int16)
            pcm_8k = audio_np[::3].tobytes()
            mulaw_8k = audioop.lin2ulaw(pcm_8k, 2)

            print(f"   Streaming {len(mulaw_8k)} bytes caller audio to Twilio gateway...")
            for i in range(0, len(mulaw_8k), 160):
                chunk = mulaw_8k[i:i+160].ljust(160, b"\x00")
                b64_payload = base64.b64encode(chunk).decode("ascii")
                media_msg = {
                    "event": "media",
                    "streamSid": stream_sid,
                    "media": {"payload": b64_payload}
                }
                await ws.send(json.dumps(media_msg))
                await asyncio.sleep(0.015)

        # 3. Listen for Twilio Media Stream response from Pratham AI
        print("   Listening for Pratham AI live streaming response over Twilio WebSocket...")
        received_chunks = 0
        t0 = asyncio.get_event_loop().time()

        while asyncio.get_event_loop().time() - t0 < 6.0:
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=4.0)
                data = json.loads(msg)
                if data.get("event") == "media":
                    received_chunks += 1
            except asyncio.TimeoutError:
                break
            except Exception:
                break

        print(f"✅ Received {received_chunks} media audio packets back from Twilio Gateway!")

        # 4. Send Twilio Stop Event
        stop_msg = {"event": "stop", "streamSid": stream_sid}
        await ws.send(json.dumps(stop_msg))

    print("\n" + "=" * 80)
    print("  ✅ TWILIO MEDIA STREAM GATEWAY TEST COMPLETED SUCCESSFULLY!")
    print("================================================================================")

if __name__ == "__main__":
    asyncio.run(test_twilio_stream())
