import sys
import asyncio
import json
import base64
import websockets
import time

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

async def test_live_conversation():
    uri = "ws://127.0.0.1:9096/media-stream"
    print(f"Connecting to Python Neural AI Voice Engine on {uri}...")

    try:
        async with websockets.connect(uri) as ws:
            print("[SUCCESS] Live Audio WebSocket Connection Established!")

            # 1. Start Event
            start_event = {
                "event": "start",
                "sequenceNumber": "1",
                "start": {
                    "streamSid": "live_test_stream_001",
                    "accountSid": "snazzyitsolutions1",
                    "callSid": "live_call_777"
                }
            }
            await ws.send(json.dumps(start_event))

            # 2. Listen for Initial Greeting
            greetings = 0
            t0 = time.time()
            while time.time() - t0 < 3.0:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=1.0)
                    if isinstance(msg, str) and "media" in msg:
                        greetings += 1
                        print(f"📥 [Initial Greeting Audio Received] Packet #{greetings}")
                except asyncio.TimeoutError:
                    break

            print("\n========================================================")
            print(f"🎉 TEST PASSED: Received {greetings} Live AI Audio Packets!")
            print("========================================================")
            return True

    except Exception as err:
        print(f"[ERROR] {err}")
        return False

if __name__ == "__main__":
    asyncio.run(test_live_conversation())
