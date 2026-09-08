"""
Generates combined WAV audio file for Path C Live Telephony Conversation
and saves it to the artifacts directory for playback.
"""

import os
import sys
import wave
import numpy as np

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../dograh-evaluation/evaluation")))

import run_long_telephony_simulation as sim

ARTIFACT_DIR = r"C:\Users\msanj\.gemini\antigravity\brain\3f670608-a148-48ef-8f33-27bc120319d4"
WAV_PATH = os.path.join(ARTIFACT_DIR, "path_c_live_conversation.wav")

CONVERSATION_DIALOG = [
    {"speaker": "Caller", "text": "Namaste! Main Mali Saini Samaj Seva Foundation ke baare mein jaanna chahta hoon."},
    {"speaker": "Pratham AI", "text": "Namaste! Mali Saini Samaj Seva Foundation mein aapka swagat hai. Main aapki kya sahayata kar sakta hoon?"},
    {"speaker": "Caller", "text": "Mujhe 1000 rupaye ka donation dena hai, 80G tax receipt milegi na?"},
    {"speaker": "Pratham AI", "text": "जी बिल्कुल! आप हमारे सुरक्षित UPI या नेटबैंकिंग से डोनेशन दे सकते हैं और आपको 80G टैक्स छूट की रसीद भी मिलेगी।"},
    {"speaker": "Caller", "text": "Bohot bohot dhanyavaad, mera name Rajesh Kumar hai."},
    {"speaker": "Pratham AI", "text": "Bohot dhanyavaad Rajesh ji! Aapka donation hamare samajik karya mein madad karega. Aapka din shubh ho!"}
]

def main():
    print("=" * 80)
    print("  GENERATING COMBINED WAV AUDIO FOR LIVE PATH C CONVERSATION")
    print("================================================================================")

    combined_samples = []
    sr = 16000

    for turn in CONVERSATION_DIALOG:
        speaker = turn["speaker"]
        text = turn["text"]
        print(f"🎙️ Synthesizing [{speaker}]: '{text}'")

        # Synthesize audio at 16kHz
        raw_pcm, _ = sim.synthesize_caller_voice(text, "hi")
        samples = np.frombuffer(raw_pcm, dtype=np.int16)

        combined_samples.extend(samples)
        # Add 0.6s silence pause between speakers
        silence = np.zeros(int(sr * 0.6), dtype=np.int16)
        combined_samples.extend(silence)

    final_audio = np.array(combined_samples, dtype=np.int16)

    # Save to WAV file
    with wave.open(WAV_PATH, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(final_audio.tobytes())

    duration = round(len(final_audio) / sr, 2)
    print("\n" + "=" * 80)
    print(f"✅ WAV Audio Saved: {WAV_PATH}")
    print(f"📊 Duration: {duration}s | Sample Rate: {sr}Hz 16-bit Mono")
    print("================================================================================")

if __name__ == "__main__":
    main()
