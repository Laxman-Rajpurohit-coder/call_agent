"""
Live Multi-Turn Long Conversation Test Script
Executes a 5-turn back-and-forth conversation with Pratham AI in Marwadi,
concatenates both caller & AI agent audio into a single seamless audio file,
and plays it out loud.
"""

import os
import sys
import time
import wave
import uuid
import struct
import asyncio
import winsound
import numpy as np

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from path_c_hybrid_agent.tts_cartesia import synthesize_speech_hd

HOST = "127.0.0.1"
PORT = 9092

TURNS = [
    {"role": "caller", "text": "राम-राम सा! माली सैनी समाज सेवा फाउंडेशन में डोनेशन रो काई तरिकौ है?"},
    {"role": "caller", "text": "80G टैक्स रसीद ईमेल पर मिलेगी काई सा?"},
    {"role": "caller", "text": "माली सैनी समाज सेवा फाउंडेशन रो ऑफिस कठे है?"},
    {"role": "caller", "text": "आपरा मैनेजर सा सूं बात करवाओ सा।"},
    {"role": "caller", "text": "घणो-घणो धन्यवाद सा! राम-राम।"}
]


async def run_long_conversation():
    print("=" * 85)
    print("  📞 STARTING LIVE LONG CONVERSATIONAL MULTI-TURN TEST CALL")
    print("  Language: Marwadi (Rajasthani Dialect)")
    print("=================================================================================\n")

    reader, writer = await asyncio.open_connection(HOST, PORT)
    
    # 1. Send AudioSocket Header (0x01 UUID)
    u_bytes = uuid.uuid4().bytes
    hdr = struct.pack("!BH", 0x01, 16)
    writer.write(hdr + u_bytes)
    await writer.drain()

    full_call_timeline = bytearray()

    # 2. Receive Initial Greeting from Pratham AI
    print("🤖 [Pratham AI]: Receiving initial Marwadi greeting...")
    greeting_pcm = bytearray()
    t0_greeting = time.perf_counter()
    while time.perf_counter() - t0_greeting < 3.0:
        try:
            g_hdr = await asyncio.wait_for(reader.readexactly(3), timeout=0.4)
            p_type, p_len = struct.unpack("!BH", g_hdr)
            p_data = await reader.readexactly(p_len)
            if p_type == 0x10:
                greeting_pcm.extend(p_data)
        except Exception:
            break

    if greeting_pcm:
        full_call_timeline.extend(greeting_pcm)
        print(f"   Greeting Received: {len(greeting_pcm)} bytes PCM")

    # 3. Loop through 5 conversational turns
    for idx, turn in enumerate(TURNS, 1):
        caller_text = turn["text"]
        print(f"\n--- Turn {idx} ---")
        print(f"🗣️ [Caller]: {caller_text}")

        # Synthesize caller audio (24kHz downsampled to 8kHz PCM)
        caller_pcm_24k = await synthesize_speech_hd(caller_text, voice_id="791d5162-d5eb-40f0-8189-f19db44611d8", sample_rate=24000)
        if not caller_pcm_24k:
            caller_pcm_24k = b"\x00" * 48000
        
        audio_np = np.frombuffer(caller_pcm_24k, dtype=np.int16)
        caller_pcm_8k = audio_np[::3].tobytes()
        full_call_timeline.extend(caller_pcm_8k)

        # Stream caller audio to gateway
        for i in range(0, len(caller_pcm_8k), 320):
            chunk = caller_pcm_8k[i:i+320].ljust(320, b"\x00")
            writer.write(struct.pack("!BH", 0x10, 320) + chunk)
            await asyncio.sleep(0.018)

        await writer.drain()

        # Stream ~500ms silence to trigger VAD turn execution
        silence_chunk = b"\x00" * 320
        for _ in range(25):
            writer.write(struct.pack("!BH", 0x10, 320) + silence_chunk)
            await asyncio.sleep(0.018)
        await writer.drain()

        # Receive Pratham AI Response Audio
        print("🤖 [Pratham AI]: Waiting for streaming response...")
        agent_response_pcm = bytearray()
        t_wait_resp = time.perf_counter()

        while time.perf_counter() - t_wait_resp < 6.0:
            try:
                r_hdr = await asyncio.wait_for(reader.readexactly(3), timeout=0.5)
                p_type, p_len = struct.unpack("!BH", r_hdr)
                p_data = await reader.readexactly(p_len)
                if p_type == 0x10:
                    agent_response_pcm.extend(p_data)
            except asyncio.TimeoutError:
                if len(agent_response_pcm) > 0:
                    break
            except Exception:
                break

        print(f"   Response Received: {len(agent_response_pcm)} bytes PCM")
        full_call_timeline.extend(agent_response_pcm)
        await asyncio.sleep(0.5)

    # Hangup Call
    writer.write(struct.pack("!BH", 0x00, 0))
    await writer.drain()
    writer.close()

    # Save Full Multi-Turn WAV Audio Artifact File
    artifact_dir = r"C:\Users\msanj\.gemini\antigravity\brain\3f670608-a148-48ef-8f33-27bc120319d4"
    wav_path = os.path.join(artifact_dir, "long_conversational_call.wav")

    with wave.open(wav_path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(8000)
        wf.writeframes(bytes(full_call_timeline))

    duration_s = round(len(full_call_timeline) / (8000 * 2), 2)
    print("\n" + "=" * 85)
    print(f"  ✅ LONG CONVERSATIONAL CALL COMPLETED (Duration: {duration_s}s)")
    print(f"  Audio File Saved to:\n     {wav_path}")
    print("=================================================================================\n")

    # Play Audio Out Loud via System Speaker
    print("🔊 Playing full long conversation audio out loud...")
    try:
        winsound.PlaySound(wav_path, winsound.SND_FILENAME)
        print("✅ Out loud playback finished!")
    except Exception as ex:
        print(f"Playback notice: {ex}")

if __name__ == "__main__":
    asyncio.run(run_long_conversation())
