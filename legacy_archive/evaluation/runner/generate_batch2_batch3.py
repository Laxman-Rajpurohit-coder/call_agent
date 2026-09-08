import wave
import numpy as np
from scipy.signal import resample_poly
import subprocess

print("Generating Batch 2 (Quiet Speech) and Batch 3 (Noise & Hallucination) audio fixtures...")

# ── Batch 2: Quiet Speech (attenuated speech, peak ~600-800, above 400 gate) ──
QUIET_SCENARIOS = [
    {
        "id": "quiet_hello_001",
        "text": "Hello, good morning.",
        "gain": 0.08,  # Attenuate amplitude to ~700 peak
        "required": ["assist", "help", "good morning"],
        "forbidden": ["goodbye"],
    },
    {
        "id": "quiet_balotra_002",
        "text": "Where is the foundation located in Balotra?",
        "gain": 0.08,
        "required": ["Gandhi Pura", "Balotra"],
        "forbidden": ["Jaipur", "Delhi"],
    },
    {
        "id": "quiet_hours_003",
        "text": "What are your opening hours?",
        "gain": 0.08,
        "required": ["9:00 AM", "5:00 PM"],
        "forbidden": ["closed"],
    },
]

for item in QUIET_SCENARIOS:
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

    # Resample to 8kHz and scale to quiet amplitude
    resampled = resample_poly(samples, 8000, rate)
    quiet_samples = (resampled * item["gain"]).astype(np.int16)

    with wave.open(out_wav, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(8000)
        wf.writeframes(quiet_samples.tobytes())

    peak = int(np.max(np.abs(quiet_samples)))
    rms = float(np.sqrt(np.mean(quiet_samples.astype(np.float32)**2)))
    print(f"  [Quiet] {s_id}: peak={peak}, rms={rms:.1f}")

    yaml_content = f"""id: {s_id}
suite: smoke
language: en
category: quiet_speech
transport: direct_audiosocket
caller_goal: quiet_speech_test
description: "Quiet Speech Scenario: {text}"

turns:
  - audio_file: "{out_wav}"

required_facts:
{chr(10).join(f'  - "{r}"' for r in item['required'])}

forbidden_facts:
{chr(10).join(f'  - "{f}"' for f in item['forbidden'])}

expected_tools: []

success_conditions:
  - stt_not_empty
  - quiet_speech_accepted
  - required_facts_present
  - forbidden_facts_absent
  - agent_audio_generated
"""
    with open(f"evaluation/scenarios/smoke/{s_id}.yaml", "w", encoding="utf-8") as yf:
        yf.write(yaml_content)


# ── Batch 3: Noise & Non-Speech Hallucination Rejection (peak < 350, max_frame_rms < 45) ──
NOISE_SCENARIOS = [
    {
        "id": "line_hiss_001",
        "type": "hiss",
        "description": "Telephony line hiss noise (peak < 300)",
    },
    {
        "id": "mic_breath_002",
        "type": "breath",
        "description": "Microphone breath puff noise (peak < 350)",
    },
    {
        "id": "mic_rub_noise_003",
        "type": "rub",
        "description": "Microphone mechanical rubbing noise (peak < 300)",
    },
    {
        "id": "pure_silence_001",
        "type": "silence",
        "description": "Pure digital silence (2.0s)",
    },
    {
        "id": "faint_whisper_noise_002",
        "type": "whisper_noise",
        "description": "Faint ambient noise testing phantom hallucination filter",
    },
    {
        "id": "room_echo_003",
        "type": "room_echo",
        "description": "Ambient room reverberation and background hum",
    },
]

np.random.seed(42)

for item in NOISE_SCENARIOS:
    s_id = item["id"]
    out_wav = f"evaluation/audio/synthetic/{s_id}.wav"
    dur_samples = 8000 * 2  # 2.0s @ 8kHz

    if item["type"] == "silence":
        samples = np.zeros(dur_samples, dtype=np.int16)
    elif item["type"] == "hiss":
        # White noise scaled to peak ~250
        noise = np.random.normal(0, 80, dur_samples)
        samples = np.clip(noise, -280, 280).astype(np.int16)
    elif item["type"] == "breath":
        # Low frequency rumble (breath puff)
        t = np.linspace(0, 2, dur_samples)
        rumble = np.sin(2 * np.pi * 60 * t) * 200 + np.random.normal(0, 40, dur_samples)
        samples = np.clip(rumble, -320, 320).astype(np.int16)
    elif item["type"] == "rub":
        # Intermittent clicks / scraping noise
        rub = np.random.normal(0, 60, dur_samples)
        # Add 3 scraping bursts
        for b in [3000, 7000, 11000]:
            rub[b:b+400] += np.random.normal(0, 180, 400)
        samples = np.clip(rub, -300, 300).astype(np.int16)
    elif item["type"] == "whisper_noise":
        # Very weak shaped noise below energy gate
        noise = np.random.normal(0, 50, dur_samples)
        samples = np.clip(noise, -200, 200).astype(np.int16)
    elif item["type"] == "room_echo":
        # 50Hz mains hum + weak background room noise
        t = np.linspace(0, 2, dur_samples)
        hum = np.sin(2 * np.pi * 50 * t) * 150 + np.random.normal(0, 50, dur_samples)
        samples = np.clip(hum, -250, 250).astype(np.int16)

    with wave.open(out_wav, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(8000)
        wf.writeframes(samples.tobytes())

    peak = int(np.max(np.abs(samples)))
    rms = float(np.sqrt(np.mean(samples.astype(np.float32)**2)))
    print(f"  [Noise] {s_id}: peak={peak}, rms={rms:.1f}")

    yaml_content = f"""id: {s_id}
suite: smoke
language: en
category: noise_rejection
transport: direct_audiosocket
caller_goal: noise_gate_test
description: "{item['description']}"

turns:
  - audio_file: "{out_wav}"

required_facts: []

forbidden_facts:
  - "I don't"
  - "I know"
  - "I love"
  - "Thank you"
  - "Gandhi Pura"
  - "Balotra"

expected_tools: []

success_conditions:
  - noise_rejected_silently
  - zero_hallucinations
  - zero_agent_playback
"""
    with open(f"evaluation/scenarios/smoke/{s_id}.yaml", "w", encoding="utf-8") as yf:
        yf.write(yaml_content)

print("Batch 2 & 3 scenario definitions and audio fixtures created successfully.")
