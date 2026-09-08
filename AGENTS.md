# Workspace Operating Rules for Superfone AI Platform

## ⚡ 1. Zero 30-Second Task Queue Fallback Rule
- Manual calls and direct campaign triggers MUST execute instantly via `asyncio.create_task(run_microsip_session(...))` inside FastAPI endpoints.
- Do NOT use blocking FastAPI `BackgroundTasks` queue for live SIP call sessions.

## 🔔 2. MicroSIP Auto-Answer vs Ringing Rules
- `autoAnswer=1`: Instant call connection (0.01s). Use for automated benchmarks & zero-latency bot demos.
- `autoAnswer=0`: Ringing sound mode. Softphone rings and waits up to 15s for user to click "Answer".

## 🛡️ 3. Environment & Import Safety
- Always ensure `import os` and `import sys` are loaded at line 1 in `microsip_direct_caller.py`.
- Keep Phase 2 Hybrid Cloud inference (`qwen/qwen3.8-27b` @ Groq Cloud) active with temperature `0.3` and Devanagari phonetic normalization (`normalize_phonetics_for_tts`).

## 🎙️ 4. Telephony Audio, STT & VAD Acoustic Rules
- **Native 8kHz Telephony WAV Headers**: Always write WAV file headers with `setframerate(8000)` for 8,000Hz PCMU telephony frames. Never set 16,000Hz headers on 8kHz PCM to prevent 2x fast chipmunk audio decoding.
- **Unblocked STT Pipeline**: Keep the STT transcription block unindented outside any `else:` statements so that gain-normalized microphone speech is 100% processed by STT.
- **Dual Cloud STT Fallback (Zero 429 Freezes)**: Use Groq Cloud `whisper-large-v3-turbo` as primary STT. If HTTP 429 rate limits occur, immediately fall back to Deepgram `nova-2` (~250ms latency) instead of waiting for CPU Faster-Whisper.
- **Multi-Path `.env` Resolution**: Always resolve `.env` across `Path(__file__).parent`, `Path(__file__).parent.parent`, and workspace root `c:\daily_works\superfone_call\.env` so API keys (`DEEPGRAM_API_KEY`, `GROQ_API_KEY`, `CARTESIA_API_KEY`) are never empty.
- **Sub-Second Response Latency (< 800ms)**: Set VAD silence cutoff to `0.35s` (350ms silence), use Deepgram Aura Direct Neural TTS with 0ms WAV header slicing (`res.content[44:]` to bypass `ffmpeg.exe` subprocess startup overhead), and cap LLM `max_tokens: 35` for fast spoken responses.
