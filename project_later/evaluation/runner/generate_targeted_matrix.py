import os
import yaml

os.makedirs("evaluation/scenarios/barge_in_noise", exist_ok=True)

# ── 1. Group 1: Agent Echo Only (5 cases) ──
for i in range(1, 6):
    data = {
        "id": f"agent_echo_only_00{i}",
        "suite": "barge_in_noise",
        "category": "agent_echo",
        "language": "en",
        "transport": "direct_audiosocket",
        "description": f"Agent echo leakage only during turn {i} - must continue speaking with 0 false barge-in stops",
        "turns": [{"audio_file": "evaluation/audio/synthetic/line_hiss_001.wav"}],
        "expected": {
            "agent_playback_completed": True,
            "barge_in_detected": False,
            "false_barge_in": False,
            "queue_underflows": 0,
            "mid_sentence_cut": False
        },
        "success_conditions": ["silent_rejection"]
    }
    with open(f"evaluation/scenarios/barge_in_noise/agent_echo_only_00{i}.yaml", "w") as f:
        yaml.dump(data, f, sort_keys=False)

# ── 2. Group 2: Line Hiss & Fan Noise Only (5 cases) ──
noise_files = [
    "line_hiss_001.wav", "faint_whisper_noise_002.wav", "room_echo_003.wav",
    "pure_silence_001.wav", "line_hiss_001.wav"
]
for i, nfile in enumerate(noise_files, start=1):
    data = {
        "id": f"noise_only_00{i}",
        "suite": "barge_in_noise",
        "category": "noise_only",
        "language": "en",
        "transport": "direct_audiosocket",
        "description": f"Ambient background noise ({nfile}) - must ignore and never trigger false barge-in",
        "turns": [{"audio_file": f"evaluation/audio/synthetic/{nfile}"}],
        "expected": {
            "agent_playback_completed": True,
            "barge_in_detected": False,
            "false_barge_in": False,
            "queue_underflows": 0
        },
        "success_conditions": ["silent_rejection"]
    }
    with open(f"evaluation/scenarios/barge_in_noise/noise_only_00{i}.yaml", "w") as f:
        yaml.dump(data, f, sort_keys=False)

# ── 3. Group 3: Breath & Mic Rub Only (5 cases) ──
rub_files = [
    "mic_breath_002.wav", "mic_rub_noise_003.wav", "mic_breath_002.wav",
    "mic_rub_noise_003.wav", "mic_breath_002.wav"
]
for i, rfile in enumerate(rub_files, start=1):
    data = {
        "id": f"breath_rub_only_00{i}",
        "suite": "barge_in_noise",
        "category": "breath_cough",
        "language": "en",
        "transport": "direct_audiosocket",
        "description": f"Caller breath or mic rub ({rfile}) - must not cut agent mid-sentence",
        "turns": [{"audio_file": f"evaluation/audio/synthetic/{rfile}"}],
        "expected": {
            "agent_playback_completed": True,
            "barge_in_detected": False,
            "false_barge_in": False,
            "mid_sentence_cut": False
        },
        "success_conditions": ["silent_rejection"]
    }
    with open(f"evaluation/scenarios/barge_in_noise/breath_rub_only_00{i}.yaml", "w") as f:
        yaml.dump(data, f, sort_keys=False)

# ── 4. Group 4: Noise + Quiet Real Speech (5 cases) ──
for i in range(1, 6):
    data = {
        "id": f"noise_plus_quiet_speech_00{i}",
        "suite": "barge_in_noise",
        "category": "quiet_speech_under_noise",
        "language": "en",
        "transport": "direct_audiosocket",
        "description": "Quiet caller speech under ambient background noise - must be accurately recognized",
        "turns": [{"audio_file": "evaluation/audio/synthetic/quiet_hello_001.wav"}],
        "required_facts": ["assist"],
        "expected": {
            "stt_not_empty": True,
            "required_facts_present": True
        },
        "success_conditions": ["stt_not_empty", "required_facts_present"]
    }
    with open(f"evaluation/scenarios/barge_in_noise/noise_plus_quiet_speech_00{i}.yaml", "w") as f:
        yaml.dump(data, f, sort_keys=False)

# ── 5. Group 5: Real Interruption during Loud Agent Speech (5 cases) ──
for i in range(1, 6):
    data = {
        "id": f"loud_agent_interruption_00{i}",
        "suite": "barge_in_noise",
        "category": "genuine_barge_in",
        "language": "en",
        "transport": "direct_audiosocket",
        "description": "Caller interrupts while agent is speaking loud address facts",
        "turns": [{"audio_file": "evaluation/audio/synthetic/opening_hours_001.wav"}],
        "barge_in": {
            "interrupt_audio": "evaluation/audio/synthetic/caller_actually_address_001.wav",
            "interrupt_after_playback_ms": 700 + i * 100
        },
        "required_facts": ["Gandhi Pura", "Balotra"],
        "expected": {
            "barge_in_detected": True,
            "playback_stopped": True,
            "interruption_complete": True
        },
        "success_conditions": ["stt_not_empty", "required_facts_present"]
    }
    with open(f"evaluation/scenarios/barge_in_noise/loud_agent_interruption_00{i}.yaml", "w") as f:
        yaml.dump(data, f, sort_keys=False)

# ── 6. Group 6: Real Interruption during Soft/Fluent Agent Speech (5 cases) ──
for i in range(1, 6):
    data = {
        "id": f"fluent_agent_interruption_00{i}",
        "suite": "barge_in_noise",
        "category": "genuine_barge_in",
        "language": "en",
        "transport": "direct_audiosocket",
        "description": "Caller interrupts during fluent conversational response",
        "turns": [{"audio_file": "evaluation/audio/synthetic/caller_no_001.wav"}],
        "barge_in": {
            "interrupt_audio": "evaluation/audio/synthetic/caller_wait_stop_001.wav",
            "interrupt_after_playback_ms": 600
        },
        "required_facts": [],
        "expected": {
            "barge_in_detected": True,
            "playback_stopped": True
        },
        "success_conditions": ["stt_not_empty"]
    }
    with open(f"evaluation/scenarios/barge_in_noise/fluent_agent_interruption_00{i}.yaml", "w") as f:
        yaml.dump(data, f, sort_keys=False)

print("Generated 30 targeted scenarios in evaluation/scenarios/barge_in_noise/")
