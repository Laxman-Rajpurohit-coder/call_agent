import urllib.request
import json
import time
import os
import wave
import sys

sys.stdout.reconfigure(encoding="utf-8")

print("=== TESTING END-TO-END HINDI TELEPHONY PIPELINE ===\n")

# 1. LLM Hindi Query
query = "नमस्ते, आपके बालोतरा ऑफिस का पता और समय क्या है?"
print(f'1. Customer Spoke (Hindi): "{query}"')

req_llm = urllib.request.Request(
    "http://127.0.0.1:9093/llm/stream",
    data=json.dumps({
        "job": {
            "call_id": "hindi_test_live",
            "tenant_id": "malisaini_001",
            "transcript": query,
            "conversation_history": []
        },
        "escalation": "LOW"
    }).encode("utf-8"),
    headers={"Content-Type": "application/json"}
)

llm_reply = ""
t0 = time.perf_counter()
with urllib.request.urlopen(req_llm) as resp:
    for line in resp:
        line_str = line.decode("utf-8").strip()
        if line_str:
            data = json.loads(line_str)
            if data.get("type") == "sentence":
                chunk_text = data.get("text")
                print(f"   [LLM Hindi Chunk]: {chunk_text}")
            elif data.get("type") == "done":
                llm_reply = data.get("full_text")

llm_latency_ms = (time.perf_counter() - t0) * 1000.0
print(f"\n2. LLM Full Hindi Response ({llm_latency_ms:.1f}ms):")
print(f'   "{llm_reply}"\n')

# 2. TTS Hindi Synthesis
req_tts = urllib.request.Request(
    "http://127.0.0.1:9095/tts",
    data=json.dumps({"text": llm_reply, "call_id": "hindi_test_live"}).encode("utf-8"),
    headers={"Content-Type": "application/json"}
)
t_tts = time.perf_counter()
with urllib.request.urlopen(req_tts) as resp_tts:
    audio_bytes = resp_tts.read()
    tts_ms = (time.perf_counter() - t_tts) * 1000.0
    dur_s = len(audio_bytes) / 16000.0
    print("3. TTS Voice Synthesis via Pratham Native Hindi:")
    print(f"   • Synthesized Audio Duration: {dur_s:.2f}s ({len(audio_bytes)} bytes)")
    print(f"   • Synthesis Time: {tts_ms:.1f}ms (RTF: {tts_ms/1000.0/dur_s:.3f})")
    
    art_dir = r"C:\Users\msanj\.gemini\antigravity\brain\3f670608-a148-48ef-8f33-27bc120319d4"
    out_wav = os.path.join(art_dir, "hindi_live_reply.wav")
    with wave.open(out_wav, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(8000)
        wf.writeframes(audio_bytes)
    print(f"   • Audio Saved to: {out_wav}")
