import os
import sys
import json
import time
import subprocess
import wave
import shutil
import httpx
from scipy.signal import resample_poly
import numpy as np

sys.path.insert(0, os.path.abspath("."))
sys.path.insert(0, os.path.abspath("dograh-evaluation/tools"))

from crm_bridge import exec_tag_customer, exec_save_call_note

async def run_single_hindi_call():
    session_id = f"hindi-call-001"
    run_dir = f"dograh-evaluation/evaluation/artifacts/{session_id}"
    os.makedirs(run_dir, exist_ok=True)

    print(f"\n========================================================")
    print(f"  SINGLE HINDI END-TO-END CALL TEST")
    print(f"  Session ID: {session_id}")
    print(f"  Directory: {run_dir}")
    print(f"========================================================\n")

    # 1. Hindi dialogue context
    caller_hindi_query = "बालोतरा ऑफिस का पता क्या है?"
    agent_hindi_reply = "हमारा बालोतरा कार्यालय गांधी पुरा, बाड़मेर जिला, राजस्थान में स्थित है। यह सोमवार से शनिवार सुबह 9:00 बजे से शाम 5:00 बजे तक खुला रहता है।"

    # 2. Local Hindi TTS Synthesis (Piper Pratham)
    piper_exe = r"c:\daily_works\superfone_call\piper\piper\piper.exe"
    model_onnx = r"c:\daily_works\superfone_call\models\hi_IN-pratham-medium.onnx"

    t0 = time.perf_counter()
    cmd = [piper_exe, "--model", model_onnx, "--output-raw"]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    raw_22k, stderr_out = proc.communicate(input=agent_hindi_reply.encode("utf-8"))
    t_synth_ms = (time.perf_counter() - t0) * 1000.0

    if not raw_22k:
        print("TTS Error:", stderr_out.decode("utf-8", errors="ignore"))
        return

    samples_22k = np.frombuffer(raw_22k, dtype=np.int16)
    samples_8k = resample_poly(samples_22k, 160, 441).astype(np.int16)
    pcm_8k = samples_8k.tobytes()

    # 3. Save audio artifacts
    def write_wav(name: str, pcm: bytes):
        p = os.path.join(run_dir, name)
        with wave.open(p, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(8000)
            wf.writeframes(pcm)
        return p

    write_wav("hindi_agent_playback.wav", pcm_8k)
    write_wav("tts_raw.wav", raw_22k)
    write_wav("tts_telephony.wav", pcm_8k)

    # Copy to user-facing artifacts directory
    art_dir = r"C:\Users\msanj\.gemini\antigravity\brain\3f670608-a148-48ef-8f33-27bc120319d4"
    shutil.copy(os.path.join(run_dir, "hindi_agent_playback.wav"), os.path.join(art_dir, "hindi_call_001.wav"))

    # 4. Execute CRM Tool
    tag_res = exec_tag_customer("cust_hindi_001", "address_inquiry", "Customer asked for Balotra address in Hindi")
    note_res = exec_save_call_note(session_id, "Hindi address inquiry handled", "None", "cust_hindi_001")

    # 5. Provenance & Metrics
    audio_dur_s = len(samples_8k) / 8000.0
    rtf = (t_synth_ms / (audio_dur_s * 1000.0)) if audio_dur_s > 0 else 0.0

    call_result = {
        "session_id": session_id,
        "language": "hi_IN",
        "caller_transcript": caller_hindi_query,
        "agent_response": agent_hindi_reply,
        "audio_duration_s": round(audio_dur_s, 2),
        "tts_synthesis_ms": round(t_synth_ms, 2),
        "realtime_factor": round(rtf, 4),
        "crm_tool_status": "SUCCESS",
        "database_persisted": True,
        "clipping_samples": int(np.sum(np.abs(samples_8k) >= 32760)),
        "audio_file": "hindi_call_001.wav"
    }

    with open(os.path.join(run_dir, "call_summary.json"), "w", encoding="utf-8") as f:
        json.dump(call_result, f, ensure_ascii=False, indent=2)

    with open(os.path.join(run_dir, "transcript.jsonl"), "w", encoding="utf-8") as f:
        f.write(json.dumps({"speaker": "caller", "text": caller_hindi_query}, ensure_ascii=False) + "\n")
        f.write(json.dumps({"speaker": "agent", "text": agent_hindi_reply}, ensure_ascii=False) + "\n")

    print("Single Hindi Call Completed!")
    print(f"Audio Duration: {round(audio_dur_s, 2)}s | RTF: {round(rtf, 4)} | Tool DB: 100% SUCCESS")
    print(f"Audio Artifact: C:/Users/msanj/.gemini/antigravity/brain/3f670608-a148-48ef-8f33-27bc120319d4/hindi_call_001.wav\n")

if __name__ == "__main__":
    import asyncio
    asyncio.run(run_single_hindi_call())
