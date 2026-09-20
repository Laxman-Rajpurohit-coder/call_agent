# Phase 0 + Phase 1 — What's in here

## What was built

```
superfone_call/
├── legacy-demo/              ← copy your working ai_bridge.py here, untouched
├── shared/
│   ├── protocol/
│   │   ├── states.py         ← CallState enum (CREATED..ENDED, FAILED)
│   │   ├── events.py         ← CallEvent enum (STT_COMPLETED, etc.)
│   │   └── messages.py       ← CallSession, STTJob/Result, LLMJob/Result,
│   │                            TTSJob/Result, EscalationLevel dataclasses
│   ├── queue/
│   │   ├── interface.py      ← JobQueue ABC (put/get/qsize) + QueueFullError
│   │   ├── local_queue.py    ← LocalAsyncQueue — Stage A, asyncio-based
│   │   └── redis_queue.py    ← Stage B stub, NotImplementedError on purpose
│   └── escalation.py         ← classify() — explicit HIGH/MEDIUM/LOW rule,
│                                not a vague "low confidence" placeholder
├── services/
│   └── call-gateway/
│       └── session.py        ← CallSessionHandler: one call = one async
│                                task, holds zero model references, moves
│                                jobs through queues with per-stage timeouts
└── docs/
    └── PHASE0_PHASE1_README.md  ← this file
```

## What's deliberately NOT built yet

- `services/stt/worker.py`, `services/llm/server.py`, `services/tts/worker.py`
  — the actual worker processes that load Whisper/Qwen/Piper once and pull
  jobs off the queues. This is the natural next step.
- The AudioSocket TCP listener that creates a `CallSessionHandler` per
  incoming Asterisk connection and feeds it audio chunks (this replaces
  the top-level loop currently in your `ai_bridge.py`).
- Redis — not needed until load testing on `LocalAsyncQueue` proves you
  need to go multi-box (Stage B).

## Why this shape

- **`shared/protocol/`** is the contract every service imports. STT, LLM,
  TTS, and the gateway all agree on the same states/events/message shapes,
  so nothing free-forms a string like `"stt_done"` in one file and
  `"transcription_finished"` in another.
- **`shared/queue/`** is queue-agnostic on purpose. `CallSessionHandler`
  only depends on the `JobQueue` interface. Swapping `LocalAsyncQueue` for
  a future `RedisQueue` implementation is a one-line change at startup —
  not a rewrite.
- **`shared/escalation.py`** makes "should this go to a human" a real,
  testable function from day one — currently simple keyword + confidence
  rules, meant to be replaced by a classifier later without changing any
  caller.
- **`CallSessionHandler`** never imports `faster_whisper`, `llama_cpp`, or
  Piper. It only knows about jobs and queues — that's the actual fix for
  "won't survive concurrent calls."

## Suggested next steps, in order

1. Write `services/stt/worker.py`: load `faster-whisper` once at startup,
   loop pulling `STTJob`s off a `LocalAsyncQueue`, push `STTResult`s to a
   results queue.
2. Same pattern for `services/llm/server.py` (Qwen2.5-1.5B via
   `llama-cpp-python`, loaded once) and `services/tts/worker.py` (Piper).
3. Write the AudioSocket entrypoint in `services/call-gateway/server.py`
   that accepts Asterisk connections, does VAD/buffering, and hands
   complete utterances to `CallSessionHandler.handle_utterance()`.
4. Run the **M1 milestone test**: 5 simultaneous simulated calls, verify
   no model is loaded per-call, no audio cross-talk, second call doesn't
   block the first. Measure STT/LLM/TTS/end-to-end latency, CPU, RAM,
   queue depth — this is the data that decides what comes next, not a
   guess.
