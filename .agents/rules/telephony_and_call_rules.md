# Superfone Telephony & Call Gateway Operational Rules

## 1. MicroSIP Auto-Answer & Timeout Rule
- **Instant Call Mode (`autoAnswer=1`)**:
  - When MicroSIP softphone is set to `autoAnswer=1` in `MicroSIP.ini`, MicroSIP accepts incoming calls in **0.01 seconds** (`200 OK`) without playing a bell ring sound.
  - Use this for automated live call testing, instant bot demos, and zero-delay call connections.
- **Manual Ringing Mode (`autoAnswer=0`)**:
  - When `autoAnswer=0`, MicroSIP plays the loud bell ringtone sound and brings the window to the front.
  - The SIP caller in `microsip_direct_caller.py` waits up to **15 seconds** for a manual click on the "Answer" button.

## 2. Preventing 30-Second Background Task Queue Delays
- **Direct Asyncio Execution**:
  - Manual calls must ALWAYS be triggered via `asyncio.create_task(run_microsip_session(...))` directly inside FastAPI routes in `services/dashboard/app/api/calls.py`.
  - NEVER enqueue manual telephony call sessions into FastAPI `BackgroundTasks` queue, as `BackgroundTasks` serializes worker tasks sequentially and introduces a 30-second delay per task.

## 3. Mandatory Imports & Error Safety
- `microsip_direct_caller.py` MUST import `os`, `sys`, `time`, `socket`, `asyncio`, `audioop`, `numpy`, `httpx`, and `re` at top of file.
- All per-turn user speech WAV recordings (`live_mic_turn_X.wav`) and full call dual-channel recordings (`recordings/{call_id}.wav`) must verify `os.makedirs(rec_dir, exist_ok=True)` safely.
