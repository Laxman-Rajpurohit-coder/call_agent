import asyncio
import struct
import time
import os
import httpx
import numpy as np

STT_URL = "http://127.0.0.1:9094/stt"
LLM_URL = "http://127.0.0.1:9093/llm"
TTS_URL = "http://127.0.0.1:9095/tts"

async def test_pipeline():
    print("\n=== Testing AI Audio Pipeline (TTS -> STT -> LLM) ===")
    
    # 1. Generate speech using TTS
    text_to_speak = "Hello, how can I help you today?"
    print(f"1. Calling TTS Server with: '{text_to_speak}'")
    async with httpx.AsyncClient() as client:
        response = await client.post(TTS_URL, json={"text": text_to_speak, "call_id": "pipeline_test"}, timeout=10.0)
        if response.status_code != 200:
            print(f"TTS failed with status: {response.status_code}")
            return None
        audio_bytes = response.content
        latency_tts = float(response.headers.get("X-Latency-MS", "0.0"))
        samples_count = len(audio_bytes) / 2
        print(f"   TTS Success: received {len(audio_bytes)} bytes of 8kHz PCM16 ({samples_count} samples, {samples_count/8000.0:.2f}s) in {latency_tts:.2f} ms")
        
    # 2. Transcribe using STT
    print(f"2. Sending generated TTS audio to STT Server...")
    async with httpx.AsyncClient() as client:
        response = await client.post(STT_URL, content=audio_bytes, timeout=10.0)
        if response.status_code != 200:
            print(f"STT failed with status: {response.status_code}")
            return None
        data = response.json()
        print(f"   STT Success: transcript='{data['text']}' | confidence_proxy={data['confidence']:.4f} | latency={data['latency_ms']:.2f} ms")
        transcript = data['text']
        stt_confidence = data['confidence']

    # 3. Process transcription with LLM
    print(f"3. Sending transcript to LLM Server...")
    payload = {
        "job": {
            "call_id": "pipeline_test",
            "tenant_id": "tenant_abc",
            "transcript": transcript,
            "conversation_history": []
        },
        "stt_confidence": stt_confidence,
        "escalation": "HIGH"
    }
    async with httpx.AsyncClient() as client:
        response = await client.post(LLM_URL, json=payload, timeout=15.0)
        if response.status_code != 200:
            print(f"LLM failed with status: {response.status_code}")
            return None
        data = response.json()
        print(f"   LLM Success: reply='{data['reply_text']}' | escalation={data['escalation']} | latency={data['latency_ms']:.2f} ms | first_token={data['first_token_ms']:.2f} ms")
        
    return audio_bytes

async def simulate_call(call_id, speech_audio_bytes):
    """Simulate 1 call connection to the AudioSocket port 9092.
    It reads and discards the welcome greeting, sends the actual spoken speech audio bytes
    to trigger STT, and streams silence frames until it receives the AI response."""
    reader, writer = await asyncio.open_connection('127.0.0.1', 9092)
    
    # Declare variables for background reader
    response_received_event = asyncio.Event()
    response_bytes_received = 0
    reader_task = None
    
    async def read_response():
        nonlocal response_bytes_received
        try:
            while True:
                hdr = await reader.readexactly(3)
                p_type, p_len = struct.unpack('!BH', hdr)
                payload = await reader.readexactly(p_len)
                if p_type == 0x10:
                    response_bytes_received += len(payload)
                    if response_bytes_received >= 15000:
                        response_received_event.set()
                        break
        except Exception:
            pass
        finally:
            response_received_event.set()

    try:
        # Write initial UUID message (Type 0x01, Length 16 bytes)
        uuid_bytes = call_id.encode('ascii').ljust(16, b'\x00')[:16]
        header = struct.pack('!BH', 0x01, len(uuid_bytes))
        writer.write(header + uuid_bytes)
        await writer.drain()
        
        # Start the response reader task immediately
        reader_task = asyncio.create_task(read_response())
                
        # 3. Send the actual spoken speech audio chunks to trigger VAD speaking state
        chunk_size = 320
        for i in range(0, len(speech_audio_bytes), chunk_size):
            chunk = speech_audio_bytes[i:i+chunk_size]
            header = struct.pack('!BH', 0x10, len(chunk))
            writer.write(header + chunk)
            await writer.drain()
            await asyncio.sleep(0.02)
            
        # 4. Stream silence frames continuously to drive the server's VAD silence timer
        silence_chunk = b'\x00' * 320
        max_loops = 600 # 12 seconds max timeout
        loop_cnt = 0
        while not response_received_event.is_set() and loop_cnt < max_loops:
            header = struct.pack('!BH', 0x10, len(silence_chunk))
            writer.write(header + silence_chunk)
            await writer.drain()
            await asyncio.sleep(0.02)
            loop_cnt += 1
            
        if not response_received_event.is_set():
            raise TimeoutError(f"Timed out waiting for AI response (received {response_bytes_received} bytes)")
            
        # Optional: verify if we actually got AI response bytes
        if response_bytes_received < 15000:
            raise RuntimeError(f"Connection ended early, only received {response_bytes_received} bytes")
            
        print(f"[Call {call_id}] Received AI response ({response_bytes_received} bytes) and finished speech turn! Success.")
        
        # Send hangup
        hangup_header = struct.pack('!BH', 0x00, 0)
        writer.write(hangup_header)
        await writer.drain()
    except Exception as e:
        import traceback
        print(f"[Call {call_id} Writer] Error:")
        traceback.print_exc()
    finally:
        if reader_task:
            reader_task.cancel()
        try:
            writer.close()
            await writer.wait_closed()
        except:
            pass

async def run_concurrency_test(speech_audio_bytes):
    print("\n=== Starting M1 Milestone Concurrency Test (5 Concurrent Calls) ===")
    start_time = time.perf_counter()
    calls = [simulate_call(f"call_{i}", speech_audio_bytes) for i in range(1, 6)]
    await asyncio.gather(*calls)
    total_time = time.perf_counter() - start_time
    print(f"\nAll 5 concurrent calls completed in {total_time:.2f} seconds.")

async def main():
    audio_bytes = await test_pipeline()
    if audio_bytes:
        await run_concurrency_test(audio_bytes)
    else:
        print("Pipeline test failed. Cannot proceed with concurrency test.")

if __name__ == '__main__':
    asyncio.run(main())
