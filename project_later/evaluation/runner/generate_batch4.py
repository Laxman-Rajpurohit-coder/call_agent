import wave
import numpy as np
from scipy.signal import resample_poly
import subprocess

print("Generating Batch 4 (Barge-In Interruption & Playback Continuity) audio fixtures...")

# ── Batch 4: Barge-In (2 audio segments: initial question + barge-in interruption) ──
# 1. barge_in_director_001: Initial query -> Agent starts explaining location -> Caller barges in asking: "Who are the directors?"
# 2. barge_in_timing_002: Initial query -> Caller barges in with "Hold on, what are the hours?"
# 3. barge_in_transfer_003: Initial query -> Caller barges in with "Can you give me the address?"

# Synthesize the interruption audio fixtures
BARGE_IN_FIXTURES = [
    {
        "id": "barge_in_director_001_initial",
        "text": "Where is the foundation located in Balotra?",
    },
    {
        "id": "barge_in_director_001_interrupt",
        "text": "Who are the directors running the foundation?",
    },
    {
        "id": "barge_in_timing_002_interrupt",
        "text": "Hold on, what are the opening hours?",
    },
    {
        "id": "barge_in_transfer_003_interrupt",
        "text": "Can you give me the office address?",
    },
]

for item in BARGE_IN_FIXTURES:
    s_id = item["id"]
    text = item["text"]
    raw_wav = f"evaluation/audio/synthetic/{s_id}_raw.wav"
    out_wav = f"evaluation/audio/synthetic/{s_id}.wav"

    cmd = f'cmd.exe /c "echo {text} | .\\piper\\piper\\piper.exe --model models\\en_US-lessac-medium.onnx --output_file {raw_wav}"'
    subprocess.run(cmd, shell=True, check=True)

    with wave.open(raw_wav, "rb") as wf:
        raw = wf.readframes(wf.getnframes())
        rate = wf.getframerate()
        samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32)

    resampled = resample_poly(samples, 8000, rate).astype(np.int16)

    with wave.open(out_wav, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(8000)
        wf.writeframes(resampled.tobytes())

# Create Scenario YAMLs for Barge-In
BARGE_SCENARIOS = [
    {
        "id": "barge_in_director_001",
        "description": "Caller interrupts agent speech after 1000ms to ask for directors",
        "initial_audio": "evaluation/audio/synthetic/barge_in_director_001_initial.wav",
        "interrupt_audio": "evaluation/audio/synthetic/barge_in_director_001_interrupt.wav",
        "interrupt_after_ms": 1000,
        "required": ["Sanjay Gahlot", "Paras Mal Gahlot"],
        "forbidden": ["Ramesh"],
    },
    {
        "id": "barge_in_timing_002",
        "description": "Caller interrupts agent speech to ask for hours, verifying <350ms stop",
        "initial_audio": "evaluation/audio/synthetic/barge_in_director_001_initial.wav",
        "interrupt_audio": "evaluation/audio/synthetic/barge_in_timing_002_interrupt.wav",
        "interrupt_after_ms": 1200,
        "required": ["9:00 AM", "5:00 PM"],
        "forbidden": ["closed"],
    },
    {
        "id": "barge_in_transfer_003",
        "description": "Caller interrupts agent speech to ask for physical address",
        "initial_audio": "evaluation/audio/synthetic/barge_in_director_001_initial.wav",
        "interrupt_audio": "evaluation/audio/synthetic/barge_in_transfer_003_interrupt.wav",
        "interrupt_after_ms": 1000,
        "required": ["Gandhi Pura", "Balotra"],
        "forbidden": ["Jaipur"],
    },
]

for b in BARGE_SCENARIOS:
    yaml_content = f"""id: {b['id']}
suite: smoke
language: en
category: barge_in
transport: direct_audiosocket
caller_goal: barge_in_interruption_test
description: "{b['description']}"

barge_in:
  initial_audio: "{b['initial_audio']}"
  interrupt_audio: "{b['interrupt_audio']}"
  interrupt_after_playback_ms: {b['interrupt_after_ms']}

required_facts:
{chr(10).join(f'  - "{r}"' for r in b['required'])}

forbidden_facts:
{chr(10).join(f'  - "{f}"' for f in b['forbidden'])}

expected_tools: []

success_conditions:
  - barge_in_detected
  - playback_halted_under_350ms
  - interruption_speech_transcribed
  - interruption_facts_present
  - zero_queue_flapping
"""
    with open(f"evaluation/scenarios/smoke/{b['id']}.yaml", "w", encoding="utf-8") as yf:
        yf.write(yaml_content)

# ── Batch 4: Continuity (Long answers & multi-turn consistency) ──
CONTINUITY_SCENARIOS = [
    {
        "id": "long_answer_address_001",
        "audio": "evaluation/audio/synthetic/foundation_address_001.wav",
        "description": "Verify multi-sentence audio chunk delivery with zero buffer underruns",
        "required": ["Gandhi Pura", "Balotra", "Barmer"],
        "forbidden": ["underrun"],
    },
    {
        "id": "multi_turn_continuity_002",
        "audio": "evaluation/audio/synthetic/foundation_directors_001.wav",
        "description": "Verify seamless multi-turn state preservation and sentence continuity",
        "required": ["Sanjay Gahlot", "Paras Mal Gahlot"],
        "forbidden": ["state_flapping"],
    },
    {
        "id": "comfort_silence_verification_003",
        "audio": "evaluation/audio/synthetic/opening_hours_001.wav",
        "description": "Verify comfort silence frame emission (2 frames, 640 bytes) upon playback completion",
        "required": ["9:00 AM", "5:00 PM"],
        "forbidden": ["audio_clipping"],
    },
]

for c in CONTINUITY_SCENARIOS:
    yaml_content = f"""id: {c['id']}
suite: smoke
language: en
category: playback_continuity
transport: direct_audiosocket
caller_goal: playback_continuity_test
description: "{c['description']}"

turns:
  - audio_file: "{c['audio']}"

required_facts:
{chr(10).join(f'  - "{r}"' for r in c['required'])}

forbidden_facts:
{chr(10).join(f'  - "{f}"' for f in c['forbidden'])}

expected_tools: []

success_conditions:
  - stt_not_empty
  - required_facts_present
  - zero_playback_underruns
  - comfort_silence_emitted
"""
    with open(f"evaluation/scenarios/smoke/{c['id']}.yaml", "w", encoding="utf-8") as yf:
        yf.write(yaml_content)

print("Batch 4 scenarios & fixtures created successfully.")
