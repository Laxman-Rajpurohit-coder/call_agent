# 🎙️ Production Voice Agent Architecture & Configuration Specification Guide

This comprehensive guide documents the architectural principles, signal processing rules, LLM guardrails, and TTS optimization techniques developed for enterprise-grade real-time voice agents.

---

## 📑 Table of Contents

1. [Architecture Overview & Signal Flow](#1-architecture-overview--signal-flow)
2. [Speech-to-Text (STT) Configuration & Noise Handling](#2-speech-to-text-stt-configuration--noise-handling)
3. [LLM Engine & Prompt Engineering Guardrails](#3-llm-engine--prompt-engineering-guardrails)
4. [Text-to-Speech (TTS) & Physical Signal DSP Mastering](#4-text-to-speech-tts--physical-signal-dsp-mastering)
5. [Concurrency, Turn-Taking & Buffer Management](#5-concurrency-turn-taking--buffer-management)
6. [Complete Production Configuration Checklists](#6-complete-production-configuration-checklists)

---

## 1. Architecture Overview & Signal Flow

```
┌─────────────────┐       AudioSocket (TCP)        ┌─────────────────────────┐
│                 │ ◄───────────────────────────► │                         │
│ PSTN / Telephony│     320-Byte PCM (20ms/8kHz)   │  Managed Hybrid Gateway │
│  (Plivo / Twilio│                               │   (Asyncio Event Loop)  │
└─────────────────┘                               └────────────┬────────────┘
                                                               │
                               ┌───────────────────────────────┴───────────────────────────────┐
                               │                                                               │
                               ▼                                                               ▼
                    ┌─────────────────────┐                                         ┌─────────────────────┐
                    │ Deepgram Nova-2 STT │                                         │ Groq LLM Streaming  │
                    │   (Linear16 8kHz)   │                                         │ (openai/gpt-oss-20b)│
                    └──────────┬──────────┘                                         └──────────┬──────────┘
                               │                                                               │
                               └───────────────────────────────┬───────────────────────────────┘
                                                               │
                                                               ▼
                                                    ┌─────────────────────┐
                                                    │ In-Memory Neural    │
                                                    │ TTS Mastering Gate  │
                                                    │ (EdgeTTS / Sonic-3) │
                                                    └─────────────────────┘
```

### Protocol Specifications
- **Transport**: TCP AudioSocket (`TCP_NODELAY = 1` disabled Nagle algorithm to prevent 320-byte packet fragmentation).
- **Frame Size**: 320 bytes per payload frame (20ms at 8kHz 16-bit mono PCM).
- **Header Structure**: `struct.pack("!BH", 0x10, length)`.

---

## 2. Speech-to-Text (STT) Configuration & Noise Handling

### Optimal API Configuration (Deepgram Nova-2)
```python
STT_CONFIG = {
    "model": "nova-2-general",
    "language": "hi", # 'hi' for Hindi, 'en' for English
    "encoding": "linear16",
    "sample_rate": 8000,
    "channels": 1,
    "smart_format": True,
    "endpointing": 300 # 300ms silence endpointing trigger
}
```

### Noise Suppression & VAD Energy Thresholds
- **Energy Threshold**: RMS $> 180$ (16-bit PCM integer level).
- **Silence Window**: `VAD_SILENCE_FRAMES = 15` (~300ms of consecutive silence below RMS threshold).
- **Phonetic Normalization**: Expand numbers and acronyms prior to processing:
  - `₹500` $\rightarrow$ `पाँच सौ रुपये`
  - `UPI` $\rightarrow$ `यू पी आई`
  - `GST` $\rightarrow$ `जी एस टी`

---

## 3. LLM Engine & Prompt Engineering Guardrails

### Model Selection & Latency
- **Primary Engine**: `openai/gpt-oss-20b` (Groq Cloud API).
- **Fallbacks**: `groq/compound-mini`, `qwen/qwen3.6-27b`.
- **Reasoning Suppression**: Filter `<think>...</think>` tags to ensure instant token streaming onset.

### System Prompt Template for Voice Agents
```markdown
You are a warm, highly fluent customer service representative.

CONVERSATIONAL RULES:
1. VARY YOUR OPENING PHRASES NATURALLY. Never repeat the same opening phrase (e.g. "जी बिल्कुल!") at the start of every sentence.
2. Use diverse openings like "जी,", "हाँ,", "अवश्य,", "निश्चिंत रहिए,", or answer the question directly.
3. Keep sentences short, concise, and expressive (max 15-20 words per response).
4. Output ONLY pure spoken Devanagari Hindi or Hinglish text.
5. STRICT TELEPHONY RULE: Never output markdown headers, bullet points, asterisks, or thinking process.
```

### Opening Phrase Deduplication Guard (Python)
```python
import random

def deduplicate_opening_phrase(text: str) -> str:
    """Strips or replaces repetitive 'जी बिल्कुल!' opening phrases."""
    if not text:
        return text
    clean_text = text.strip()
    if clean_text.startswith("जी बिल्कुल!") or clean_text.startswith("जी बिल्कुल,") or clean_text.startswith("जी बिल्कुल"):
        remainder = clean_text.replace("जी बिल्कुल!", "").replace("जी बिल्कुल,", "").replace("जी बिल्कुल", "").strip()
        new_opener = random.choice(["जी,", "हाँ,", "अवश्य,", "निश्चिंत रहिए,", "बिल्कुल,"])
        return f"{new_opener} {remainder}".strip()
    return clean_text
```

---

## 4. Text-to-Speech (TTS) & Physical Signal DSP Mastering

### The 4 Principles of Pristine Telephony Audio
1. **Dynamic Headroom Peak Target (-18dBFS / -20dBFS)**:
   Scale peak audio amplitude to `0.125` (max target) before passing through a hyperbolic tangent (`np.tanh`) soft limiter. This eliminates 100% of digital peak square-wave clipping across high-consonant bursts.
2. **G.712 Telephony Bandpass Filter**:
   Apply a 2nd-order 300Hz Butterworth High-Pass filter and 4th-order 3.4kHz Low-Pass filter to strip sub-bass mic thumps and ultrasonic carrier hiss.
3. **Orator Speaking Cadence (`rate="+15%"` / 4.0 Syllables/Sec)**:
   Increase neural TTS rate to `+15%` to transform slow, monotonic reading into a dynamic, engaging human orator cadence.
4. **30ms Cosine Raised Hanning End-Fade**:
   Apply a 30ms Cosine fade-out at the tail of every sentence response with a micro 20ms silence cushion to eliminate mid-word truncations and subprocess spawn delays.

### Master DSP Implementation Code (Python)
```python
import numpy as np
from scipy import signal
import io
from pydub import AudioSegment

async def synthesize_mastered_neural_pcm(text: str, voice: str = "hi-IN-SwaraNeural", rate: str = "+15%") -> bytes:
    import edge_tts
    
    communicate = edge_tts.Communicate(text, voice, rate=rate)
    mp3_bytes = bytearray()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            mp3_bytes.extend(chunk["data"])

    if not mp3_bytes:
        return b""

    # 1. In-Memory MP3 to PCM Decoding (0 Disk I/O)
    audio = AudioSegment.from_file(io.BytesIO(bytes(mp3_bytes)), format="mp3")
    audio = audio.set_frame_rate(24000).set_channels(1).set_sample_width(2)
    raw_pcm = audio.raw_data

    usable_len = (len(raw_pcm) // 2) * 2
    samples_float = np.frombuffer(raw_pcm[:usable_len], dtype=np.int16).astype(np.float64) / 32768.0

    # 2. -18dBFS Dynamic Headroom Scaling (Peak Target = 0.125)
    max_peak = np.max(np.abs(samples_float))
    if max_peak > 0:
        samples_scaled = (samples_float / max_peak) * 0.125
    else:
        samples_scaled = samples_float

    # 3. Soft Limiter & G.712 Bandpass Filter (300Hz HP + 3.4kHz LP)
    samples_limited = np.tanh(samples_scaled) * 0.85
    nyquist = 12000.0 # 24kHz / 2
    b_hp, a_hp = signal.butter(2, 300.0 / nyquist, btype='high')
    samples_hp = signal.filtfilt(b_hp, a_hp, samples_limited)

    b_lp, a_lp = signal.butter(4, min(3400.0 / nyquist, 0.95), btype='low')
    samples_clean = signal.filtfilt(b_lp, a_lp, samples_hp)

    # 4. Resample to 8kHz Target Rate
    resampled = signal.resample_poly(samples_clean, 8000, 24000)

    # 5. 30ms Cosine End-Fade & 20ms Silence Cushion
    n_out = min(240, len(resampled) // 4)
    if n_out > 0:
        resampled[-n_out:] *= np.cos(np.linspace(0, np.pi / 2, n_out))

    cushion = np.zeros(160, dtype=np.float64)
    final_float = np.concatenate([resampled, cushion])

    return np.clip(final_float * 32767.0, -32767, 32767).astype(np.int16).tobytes()
```

---

## 5. Concurrency, Turn-Taking & Buffer Management

### Eliminating Dual Speech Overlap
- **Sequential Turn Lock (`asyncio.Lock()`)**:
  Enforce a turn lock on every active call session so that ONLY ONE response can be processed and streamed at a time.

---

## 8. Physical Packet Protocol & Buffer Configuration Specification

### A. Mic -> STT Packet Pipeline (Inbound Path)
```
[MicroSIP Softphone]
    │  G.711 mu-law RTP (UDP 8000)
    │  • Payload Type: 0 (PCMU)
    │  • Packet Size: 160 bytes (20ms audio)
    │  • Sampling Rate: 8,000 Hz
    ▼
[Gateway G.711 Decoder & Gain Gate]
    │  • Mu-Law -> 16-bit Linear PCM (320 bytes / 20ms)
    │  • Dynamic Gain Boost: 5.0x Peak Scaling
    │  • VAD Energy Gate: RMS > 50 (200ms silence endpointing)
    ▼
[Deepgram Nova-2 STT HTTP/2 Stream]
    │  • Content-Type: audio/raw
    │  • Encoding: linear16, 8000Hz mono
    │  • Network: Persistent HTTP/2 Connection Pool (<150ms latency)
```

### B. TTS -> Speaker Packet Pipeline (Outbound Path)
```
[Neural TTS Engine (hi-IN-SwaraNeural)]
    │  • Native Rate: 24,000 Hz 16-bit Mono (rate="+15%")
    ▼
[DSP Mastering Gate]
    │  • Peak Target: 0.125 (-18dBFS headroom scaling)
    │  • Filter: G.712 Telephony Bandpass (300Hz HP + 3.4kHz LP)
    │  • Tail Fade: 30ms Cosine Raised Hanning + 20ms Cushion
    │  • Resampler: Polyphase Sinc 24kHz -> 8kHz
    ▼
[G.711 Mu-Law RTP Encoder]
    │  • Linear PCM -> 160 bytes PCMU per frame
    │  • RTP Header (12 bytes): Version=2, PT=0, SeqNum(+1), TS(+160)
    │  • Async Pacing: 18-20ms frame scheduler (await asyncio.sleep(0.018))
    ▼
[MicroSIP Softphone / PC Speakers]
```


