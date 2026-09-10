import sys
import asyncio
import json
import base64
import websockets
import time

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

async def test_full_pipeline():
    uri = "ws://127.0.0.1:8080/media-stream"
    print(f"Connecting to Node Proxy on {uri}...")

    try:
        async with websockets.connect(uri) as ws:
            print("[SUCCESS] Proxy WebSocket Connection Opened successfully!")

            # Send Exotel Start Event
            start_event = {
                "event": "start",
                "sequenceNumber": "1",
                "start": {
                    "streamSid": "test_verification_stream_123",
                    "accountSid": "snazzyitsolutions1",
                    "callSid": "test_call_999",
                    "tracks": ["inbound"],
                    "mediaFormat": {
                        "encoding": "audio/x-mulaw",
                        "sampleRate": 8000,
                        "channels": 1
                    }
                }
            }
            await ws.send(json.dumps(start_event))
            print("[SENT] Sent 'start' event packet to proxy.")

            received_frames = 0
            has_media_payload = False

            t0 = time.time()
            while time.time() - t0 < 6.0:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=3.0)
                    received_frames += 1
                    print(f"[RECV #{received_frames}] Type: {type(msg).__name__}, Length: {len(msg)}")
                    if isinstance(msg, str) and "media" in msg and "payload" in msg:
                        data = json.loads(msg)
                        payload_b64 = data.get("media", {}).get("payload", "")
                        if len(payload_b64) > 10:
                            has_media_payload = True
                            print(f"[SUCCESS] Exotel Base64 Media Payload Verified via Proxy ({len(payload_b64)} chars)!")
                            break
                except asyncio.TimeoutError:
                    print("Timeout waiting for frame...")
                    break

            if has_media_payload:
                print("\n========================================================")
                print("🎉 FULL VERIFICATION PASSED: End-to-End Audio Stream Verified!")
                print("========================================================")
                return True
            else:
                print(f"[FAIL] Received {received_frames} frames.")
                return False

    except Exception as err:
        print(f"[ERROR] Connection error: {err}")
        return False

if __name__ == "__main__":
    asyncio.run(test_full_pipeline())
