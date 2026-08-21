import wave
import numpy as np
from scipy.signal import resample_poly
import httpx
import subprocess

BATCH1 = [
    {
        "id": "opening_hours_001",
        "text": "What are your opening hours and working days?",
        "intent": "opening_hours",
        "required": ["9:00 AM", "5:00 PM"],
        "forbidden": ["24 hours", "closed on Saturday"],
    },
    {
        "id": "foundation_directors_001",
        "text": "Who are the directors running the foundation?",
        "intent": "foundation_directors",
        "required": ["Sanjay Gahlot", "Paras Mal Gahlot"],
        "forbidden": ["Ramesh", "Mukesh"],
    },
    {
        "id": "donation_inquiry_001",
        "text": "How can I make a donation to support the foundation?",
        "intent": "donation_inquiry",
        "required": ["donation", "support"],
        "forbidden": ["paytm 99999", "credit card only"],
    },
    {
        "id": "volunteer_inquiry_001",
        "text": "I would like to volunteer and help the foundation.",
        "intent": "volunteer_inquiry",
        "required": ["volunteer", "welcome"],
        "forbidden": ["no volunteers needed"],
    },
    {
        "id": "hospital_education_001",
        "text": "What services do you provide for education and medical care?",
        "intent": "hospital_education",
        "required": ["education", "medical"],
        "forbidden": ["we do not offer services"],
    },
    {
        "id": "contact_number_001",
        "text": "Can you give me the foundation contact phone number?",
        "intent": "contact_number",
        "required": ["receptionist", "Gandhi Pura"],
        "forbidden": ["9876543210", "1234567890"],
    },
    {
        "id": "greeting_aloha_001",
        "text": "Aloha, good day.",
        "intent": "greeting",
        "required": ["assist", "help"],
        "forbidden": ["goodbye", "hangup"],
    },
    {
        "id": "gratitude_closure_001",
        "text": "Thank you so much for the information.",
        "intent": "gratitude_closure",
        "required": ["welcome", "help"],
        "forbidden": ["angry", "error"],
    },
    {
        "id": "human_transfer_001",
        "text": "Can you please transfer my call to a human receptionist?",
        "intent": "human_transfer",
        "required": ["transfer", "receptionist"],
        "forbidden": ["cannot transfer"],
    },
]

print(f"Synthesizing and registering {len(BATCH1)} Batch 1 scenarios...")

for item in BATCH1:
    s_id = item["id"]
    text = item["text"]
    wav_path = f"evaluation/audio/synthetic/{s_id}.wav"
    
    # 1. Synthesize via piper.exe CLI
    cmd = f'cmd.exe /c "echo {text} | .\\piper\\piper\\piper.exe --model models\\en_US-lessac-medium.onnx --output_file {wav_path}"'
    subprocess.run(cmd, shell=True, check=True)
    
    # 2. Resample to 8kHz telephony PCM
    with wave.open(wav_path, "rb") as wf:
        raw = wf.readframes(wf.getnframes())
        rate = wf.getframerate()
        samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32)

    resampled = resample_poly(samples, 8000, rate).astype(np.int16)

    with wave.open(wav_path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(8000)
        wf.writeframes(resampled.tobytes())

    # 3. Create Scenario YAML
    yaml_content = f"""id: {s_id}
suite: smoke
language: en
category: normal
transport: direct_audiosocket
caller_goal: {item['intent']}
description: "Batch 1 Scenario: {text}"

turns:
  - audio_file: "{wav_path}"

allowed_facts:
  - "Gandhi Pura"
  - "Balotra"
  - "Barmer"
  - "Rajasthan"

required_facts:
{chr(10).join(f'  - "{r}"' for r in item['required'])}

forbidden_facts:
{chr(10).join(f'  - "{f}"' for f in item['forbidden'])}

expected_tools: []

success_conditions:
  - stt_not_empty
  - required_facts_present
  - forbidden_facts_absent
  - agent_audio_generated
"""
    with open(f"evaluation/scenarios/smoke/{s_id}.yaml", "w", encoding="utf-8") as yf:
        yf.write(yaml_content)

    print(f"  [OK] Generated scenario & fixture for: {s_id}")

print("Batch 1 fixtures generated successfully.")
