import os
import sys
import json
import time
import wave
import shutil
import asyncio
import subprocess
from scipy.signal import resample_poly
import numpy as np

try:
    import winsound
    HAS_WINSOUND = True
except ImportError:
    HAS_WINSOUND = False

sys.path.insert(0, os.path.abspath("."))
sys.path.insert(0, os.path.abspath("dograh-evaluation/tools"))

from crm_bridge import exec_tag_customer, exec_save_call_note, exec_schedule_callback

# Supervisor Conversation Scenario (Multi-Turn with Hindi & English, Interruption, and Tools)
CONVERSATION_TURNS = [
    {
        "turn": 1,
        "speaker": "Caller",
        "text": "Hello, good morning! Is this the Malisaini Samaj Seva Foundation?",
        "lang": "en",
        "tts_text": "Good morning! Yes, this is Malisaini Samaj Seva Foundation. How can I help you today?"
    },
    {
        "turn": 2,
        "speaker": "Caller",
        "text": "बालोतरा ऑफिस का एड्रेस और टाइमिंग बता दीजिए।",
        "lang": "hi",
        "tts_text": "हमारा बालोतरा कार्यालय गांधी पुरा, बाड़मेर जिला, राजस्थान में स्थित है। यह सोमवार से शनिवार सुबह 9:00 बजे से शाम 5:00 बजे तक खुला रहता है।"
    },
    {
        "turn": 3,
        "speaker": "Caller (Interrupting)",
        "text": "Actually, I need to speak to Sanjay Gahlot directly. Can you schedule a callback?",
        "lang": "en",
        "tts_text": "Certainly! I have scheduled a priority callback with Director Sanjay Gahlot for Monday morning.",
        "tool_action": lambda: exec_schedule_callback("cust_sup_001", "+919876543210", "2026-08-24T10:00:00Z")
    },
    {
        "turn": 4,
        "speaker": "Caller",
        "text": "Thank you so much. Have a great day!",
        "lang": "en",
        "tts_text": "You are most welcome! Have a wonderful day ahead.",
        "tool_action": lambda: exec_save_call_note("call_sup_001", "Balotra address & Director Sanjay Gahlot callback requested", "Callback scheduled", "cust_sup_001")
    }
]

def synthesize_piper(text: str, lang: str = "en") -> bytes:
    piper_exe = r"c:\daily_works\superfone_call\piper\piper\piper.exe"
    if lang == "hi":
        model_onnx = r"c:\daily_works\superfone_call\models\hi_IN-pratham-medium.onnx"
    else:
        model_onnx = r"c:\daily_works\superfone_call\models\en_US-lessac-medium.onnx"

    cmd = [piper_exe, "--model", model_onnx, "--output-raw"]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    raw_22k, _ = proc.communicate(input=text.encode("utf-8"))
    
    if not raw_22k:
        return b"\x00\x00" * 8000
    
    samples_22k = np.frombuffer(raw_22k, dtype=np.int16)
    samples_8k = resample_poly(samples_22k, 160, 441).astype(np.int16)
    return samples_8k.tobytes()

def run_supervisor_simulation(play_audio_live: bool = True):
    run_id = f"supervisor-sim-{int(time.time())}"
    art_dir = r"C:\Users\msanj\.gemini\antigravity\brain\3f670608-a148-48ef-8f33-27bc120319d4"
    out_wav = os.path.join(art_dir, "supervisor_live_call_mix.wav")

    print("\n" + "=" * 70)
    print("  SUPERVISOR LIVE CALL SIMULATION & QUALITY MONITOR")
    print(f"  Session ID: {run_id}")
    print("  Live Speaker Playback: ENABLED" if play_audio_live else "  Live Speaker Playback: DISABLED")
    print("=" * 70 + "\n")

    full_conversation_pcm = []

    for item in CONVERSATION_TURNS:
        turn_num = item["turn"]
        caller_txt = item["text"]
        agent_txt = item["tts_text"]
        lang = item["lang"]

        print(f"\n--- [TURN {turn_num}] ---")
        try:
            print(f"[CALLER]: \"{caller_txt}\"")
        except Exception:
            print(f"[CALLER]: {caller_txt.encode('ascii', 'replace').decode('ascii')}")
        time.sleep(0.4)

        # Synthesize Agent Response
        t0 = time.perf_counter()
        agent_pcm = synthesize_piper(agent_txt, lang=lang)
        synth_time_ms = (time.perf_counter() - t0) * 1000.0
        dur_s = len(agent_pcm) / (8000 * 2)

        try:
            print(f"[AGENT ({lang.upper()})]: \"{agent_txt}\" (Latency: {synth_time_ms:.1f}ms, Audio: {dur_s:.2f}s)")
        except Exception:
            print(f"[AGENT ({lang.upper()})]: Audio: {dur_s:.2f}s (Latency: {synth_time_ms:.1f}ms)")

        # Execute Tool if present
        if "tool_action" in item:
            tool_res = item["tool_action"]()
            print(f"[CRM TOOL]: {tool_res.get('status')} -> {tool_res.get('customer_id', '')}")

        # Append to master recording (with 300ms pause)
        full_conversation_pcm.append(agent_pcm)
        full_conversation_pcm.append(b"\x00\x00" * int(8000 * 0.35))

        # Live Playback on Windows speaker
        if play_audio_live and HAS_WINSOUND:
            temp_turn_wav = os.path.join(art_dir, f"temp_turn_{turn_num}.wav")
            with wave.open(temp_turn_wav, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(8000)
                wf.writeframes(agent_pcm)
            try:
                winsound.PlaySound(temp_turn_wav, winsound.SND_FILENAME)
            except Exception:
                pass
            if os.path.exists(temp_turn_wav):
                try: os.remove(temp_turn_wav)
                except Exception: pass

    # Write Master Mixed Audio File
    master_bytes = b"".join(full_conversation_pcm)
    with wave.open(out_wav, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(8000)
        wf.writeframes(master_bytes)

    total_dur_s = len(master_bytes) / (8000 * 2)
    print("\n" + "=" * 70)
    print(f"  SIMULATION COMPLETED (Total Call Duration: {total_dur_s:.2f}s)")
    print(f"  Master Recording Saved: {out_wav}")
    print("=" * 70 + "\n")
    return out_wav

if __name__ == "__main__":
    play_live = "--no-audio" not in sys.argv
    run_supervisor_simulation(play_audio_live=play_live)
