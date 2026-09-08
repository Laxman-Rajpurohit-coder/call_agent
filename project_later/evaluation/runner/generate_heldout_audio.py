import os
import wave
import numpy as np
from scipy.signal import resample_poly, butter, lfilter
import subprocess

os.makedirs("evaluation/audio/held_out", exist_ok=True)
os.makedirs("evaluation/scenarios/held_out", exist_ok=True)
os.makedirs("evaluation/scenarios/validation", exist_ok=True)

# ── 1. Acoustic Signal Processing Utilities ─────────────────────────────────

def butter_bandpass(lowcut, highcut, fs, order=4):
    nyq = 0.5 * fs
    low = lowcut / nyq
    high = highcut / nyq
    b, a = butter(order, [low, high], btype='band')
    return b, a

def apply_phone_speaker_filter(samples, fs=8000):
    """Simulates telephony/speaker frequency response (300Hz - 3400Hz bandpass + resonance)."""
    b, a = butter_bandpass(300, 3400, fs, order=3)
    filtered = lfilter(b, a, samples)
    return filtered

def simulate_room_reverberation(samples, decay=0.3, delays_ms=[15, 35, 60, 95]):
    """Simulates physical acoustic room reflections and leakage into microphone."""
    out = samples.copy()
    fs = 8000
    for i, d in enumerate(delays_ms):
        delay_samples = int(d * fs / 1000.0)
        gain = (decay ** (i + 1)) * (0.8 if i % 2 == 0 else -0.7)
        if len(samples) > delay_samples:
            delayed = np.pad(samples[:-delay_samples], (delay_samples, 0), mode='constant')
            out += delayed * gain
    return out

def generate_noise(noise_type: str, duration_s: float, fs: int = 8000, rms_target: float = 300.0) -> np.ndarray:
    n_samples = int(duration_s * fs)
    if noise_type == "line_hiss":
        # Brownian / 1/f noise
        white = np.random.randn(n_samples)
        b, a = butter(1, 0.05, btype='low')
        noise = lfilter(b, a, white)
    elif noise_type == "fan_ac_hum":
        # 50Hz fundamental + 100Hz harmonic + broadband rumble
        t = np.linspace(0, duration_s, n_samples)
        hum = 0.6 * np.sin(2 * np.pi * 50 * t) + 0.3 * np.sin(2 * np.pi * 100 * t)
        noise = hum + 0.2 * np.random.randn(n_samples)
    elif noise_type == "traffic_rumble":
        white = np.random.randn(n_samples)
        b, a = butter(2, 0.08, btype='low')
        noise = lfilter(b, a, white)
    else:  # white
        noise = np.random.randn(n_samples)

    current_rms = np.sqrt(np.mean(noise**2))
    if current_rms > 0:
        noise = noise * (rms_target / current_rms)
    return noise.astype(np.float32)

def save_wav(samples: np.ndarray, filepath: str, fs: int = 8000):
    samples = np.clip(samples, -32767, 32767).astype(np.int16)
    with wave.open(filepath, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(fs)
        wf.writeframes(samples.tobytes())

# ── 2. Synthesize Unseen Speech & Generate Noise-Mixed Held-Out Audio ────────

def tts_generate(text: str, model_path: str = "models/en_US-lessac-medium.onnx") -> np.ndarray:
    temp_raw = "evaluation/audio/held_out/temp_tts.wav"
    cmd = f'cmd.exe /c "echo {text} | .\\piper\\piper\\piper.exe --model {model_path} --output_file {temp_raw}"'
    subprocess.run(cmd, shell=True, check=True)
    with wave.open(temp_raw, "rb") as wf:
        raw = wf.readframes(wf.getnframes())
        rate = wf.getframerate()
        samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
    if os.path.exists(temp_raw):
        os.remove(temp_raw)
    return resample_poly(samples, 8000, rate)

def mix_audio_and_noise(speech: np.ndarray, noise_type: str, snr_db: float = 10.0) -> np.ndarray:
    n_samples = len(speech)
    dur = n_samples / 8000.0
    speech_rms = np.sqrt(np.mean(speech**2))
    target_noise_rms = speech_rms / (10 ** (snr_db / 20.0))
    noise = generate_noise(noise_type, dur, rms_target=target_noise_rms)
    if len(noise) < n_samples:
        noise = np.pad(noise, (0, n_samples - len(noise)))
    else:
        noise = noise[:n_samples]
    return speech + noise

# ── 3. Build Held-Out Matrix (20 Independent Scenarios) ───────────────────────

held_out_scenarios = [
    # Group A: Realistic Acoustic Echo (Non-Bit-Identical Leakage)
    {
        "id": "heldout_echo_speaker_001",
        "category": "agent_echo",
        "desc": "Realistic phone speaker acoustic echo (filtered + reverberation) during address",
        "gen_audio": lambda: simulate_room_reverberation(apply_phone_speaker_filter(tts_generate("The foundation is in Balotra")), decay=0.35) * 0.4,
    },
    {
        "id": "heldout_echo_laptop_002",
        "category": "agent_echo",
        "desc": "Laptop speaker acoustic leakage during directors response",
        "gen_audio": lambda: simulate_room_reverberation(tts_generate("Sanjay Gahlot and Paras Mal Gahlot"), decay=0.25) * 0.3,
    },
    {
        "id": "heldout_echo_lowgain_003",
        "category": "agent_echo",
        "desc": "Low-gain room boundary echo during hours",
        "gen_audio": lambda: simulate_room_reverberation(tts_generate("Our office hours are from 9 to 5"), decay=0.4) * 0.2,
    },
    # Group B: Independent Noise Conditions (Fan, Traffic, Hum)
    {
        "id": "heldout_noise_fan_ac_001",
        "category": "noise_only",
        "desc": "Continuous 50Hz AC hum and fan noise (RMS=450)",
        "gen_audio": lambda: generate_noise("fan_ac_hum", 3.0, rms_target=450.0),
    },
    {
        "id": "heldout_noise_traffic_002",
        "category": "noise_only",
        "desc": "Low-frequency roadside traffic rumble (RMS=380)",
        "gen_audio": lambda: generate_noise("traffic_rumble", 3.5, rms_target=380.0),
    },
    {
        "id": "heldout_noise_line_hiss_003",
        "category": "noise_only",
        "desc": "Telephony line hiss noise (RMS=280)",
        "gen_audio": lambda: generate_noise("line_hiss", 3.0, rms_target=280.0),
    },
    # Group C: Quiet Caller Speech mixed with Noise at +10dB and +5dB SNR
    {
        "id": "heldout_quiet_speech_snr10_001",
        "category": "quiet_speech_under_noise",
        "desc": "Quiet caller asking for Balotra address at +10dB SNR over AC noise",
        "gen_audio": lambda: mix_audio_and_noise(tts_generate("Where is the Balotra office located?") * 0.5, "fan_ac_hum", 10.0),
        "required_facts": ["Gandhi Pura", "Balotra"],
    },
    {
        "id": "heldout_quiet_speech_snr5_002",
        "category": "quiet_speech_under_noise",
        "desc": "Quiet caller asking for working hours at +5dB SNR over traffic rumble",
        "gen_audio": lambda: mix_audio_and_noise(tts_generate("What are your opening hours?") * 0.4, "traffic_rumble", 5.0),
        "required_facts": ["9:00 AM", "5:00 PM"],
    },
    # Group D: Genuine Interruptions over Agent Playback
    {
        "id": "heldout_interrupt_wait_please_001",
        "category": "genuine_barge_in",
        "desc": "Real caller interrupts agent with 'No, tell me the address please'",
        "gen_audio": lambda: tts_generate("No, tell me the address please."),
        "required_facts": ["Gandhi Pura", "Balotra"],
    },
    {
        "id": "heldout_interrupt_human_handoff_002",
        "category": "genuine_barge_in",
        "desc": "Real caller interrupts with 'Can I speak with a coordinator?'",
        "gen_audio": lambda: tts_generate("Can I speak with a coordinator please?"),
        "required_facts": [],
    },
]

print(f"Generating {len(held_out_scenarios)} held-out audio fixtures and scenario definitions...")

for sc in held_out_scenarios:
    s_id = sc["id"]
    audio_path = f"evaluation/audio/held_out/{s_id}.wav"
    samples = sc["gen_audio"]()
    save_wav(samples, audio_path)

    scenario_yaml = f"""id: {s_id}
suite: held_out
category: {sc['category']}
language: en
transport: direct_audiosocket
description: "{sc['desc']}"

turns:
  - audio_file: "{audio_path}"

required_facts: {sc.get('required_facts', [])}
forbidden_facts: []

expected_tools: []
"""
    with open(f"evaluation/scenarios/held_out/{s_id}.yaml", "w", encoding="utf-8") as yf:
        yf.write(scenario_yaml)

print("Held-out test set generation complete.")
