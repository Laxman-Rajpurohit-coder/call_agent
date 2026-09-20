import os
import sys
import wave
import shutil
import json
from faster_whisper import WhisperModel

src_wav = r"c:\daily_works\superfone_call\recordings\0d54b337-9875-fa64-254c-29fdc0c76497-20260822-075727.wav"
art_dir = r"C:\Users\msanj\.gemini\antigravity\brain\3f670608-a148-48ef-8f33-27bc120319d4"
dst_wav = os.path.join(art_dir, "live_call_0d54b337.wav")

if os.path.exists(src_wav):
    shutil.copy(src_wav, dst_wav)
    print("Copied recording to artifact directory.")

    print("Running Faster-Whisper turn-by-turn transcription on live recording...")
    model = WhisperModel("base.en", device="cpu", compute_type="int8")
    
    segments, info = model.transcribe(dst_wav, beam_size=3)
    print(f"Detected Language: {info.language} (Probability: {info.language_probability:.2f})")
    
    transcript_items = []
    print("\n=== TURN-BY-TURN TRANSCRIPT ===")
    for s in segments:
        item = {"start": round(s.start, 2), "end": round(s.end, 2), "text": s.text.strip()}
        transcript_items.append(item)
        print(f"[{item['start']:06.2f}s - {item['end']:06.2f}s] {item['text']}")
        
    out_json = os.path.join(art_dir, "live_call_0d54b337_transcript.json")
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(transcript_items, f, indent=2, ensure_ascii=False)
    print(f"\nTranscript saved to {out_json}")
