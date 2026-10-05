import socket
import struct
import asyncio
import logging
import os
import re
import sys
import time
import httpx
import numpy as np
from typing import Optional, Dict, Set, Any
from datetime import datetime, timezone
from shared.protocol import CallSession, CallState, STTResult, LLMResult, TTSResult
from shared.queue.local_queue import LocalAsyncQueue
from shared.queue.interface import QueueFullError
from services.call_gateway.session import CallSessionHandler, CallFailedError
from services.call_gateway.vad_detector import SileroEndpointingEngine, VADState
from services.dashboard.app.services.call_lifecycle import astart_call, aend_call, aheartbeat_call

# ── Logging ──────────────────────────────────────────────────────────────────

try:
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True, errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", line_buffering=True, errors="replace")
except Exception:
    pass

# Same file the dashboard's live monitor tails (settings.CALL_GATEWAY_LOG): one source of truth,
# so the gateway can never write to a different log than the one the dashboard reads.
from services.dashboard.app.config import settings as _dashboard_settings
_LOG_PATH = _dashboard_settings.CALL_GATEWAY_LOG
os.makedirs(os.path.dirname(os.path.abspath(_LOG_PATH)), exist_ok=True)
file_handler = logging.FileHandler(_LOG_PATH, encoding="utf-8")
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(name)s - %(message)s'))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout), file_handler]
)
logger = logging.getLogger("call_gateway.server")

# ── Service URLs ──────────────────────────────────────────────────────────────

LLM_SERVICE_URL = "http://127.0.0.1:9093/llm"
STT_SERVICE_URL = "http://127.0.0.1:9094/stt"
TTS_SERVICE_URL = "http://127.0.0.1:9095/tts"

# ── Global Admission Control ──────────────────────────────────────────────────
#
# Process-local atomic counter guarded by asyncio.Lock.
#
# SCOPE BOUNDARY: This counter enforces the limit correctly while exactly one
# gateway process is running. When the gateway is horizontally scaled across
# multiple processes or hosts, each process maintains its own counter and the
# aggregate admission limit is no longer enforced globally. A distributed
# admission mechanism (e.g. Redis atomic counter) is required at that point.
# This is a named future item; Phase 3 runs a single gateway process.
#
# Configured via MAX_CONCURRENT_CALLS environment variable.
MAX_CONCURRENT_CALLS = int(os.environ.get("MAX_CONCURRENT_CALLS", "10"))
_active_calls: int = 0
_active_calls_lock: asyncio.Lock | None = None   # initialized in main()


async def _try_admit(peer) -> bool:
    global _active_calls
    async with _active_calls_lock:
        if _active_calls >= MAX_CONCURRENT_CALLS:
            logger.warning(
                "ADMISSION_REJECTED peer=%s active=%d limit=%d",
                peer, _active_calls, MAX_CONCURRENT_CALLS,
            )
            return False
        _active_calls += 1
        logger.info(
            "ADMISSION_ACCEPTED peer=%s active=%d limit=%d",
            peer, _active_calls, MAX_CONCURRENT_CALLS,
        )
        return True


async def _release_call() -> None:
    global _active_calls
    async with _active_calls_lock:
        _active_calls -= 1

# ── Utilities ─────────────────────────────────────────────────────────────────

def get_audio_energy(audio_bytes):
    """Calculate RMS energy of 16-bit PCM audio frame."""
    import numpy as np
    samples = import_np_frombuffer(audio_bytes)
    if len(samples) == 0:
        return 0
    return __import__('numpy').sqrt(__import__('numpy').mean(samples.astype(__import__('numpy').float64)**2))

def get_audio_energy(audio_bytes):
    import numpy as np
    samples = np.frombuffer(audio_bytes, dtype=np.int16)
    if len(samples) == 0:
        return 0
    return np.sqrt(np.mean(samples.astype(np.float64)**2))

# ── Service bridge tasks ──────────────────────────────────────────────────────

async def bridge_stt_queue(job_queue, results_queue, http_client):
    """Bridge for STT requests: pulls STTJob, calls STT service, puts STTResult."""
    while True:
        try:
            job = await job_queue.get()
            enqueue_time = time.time()   # wall-clock for cross-process queue-wait
            t_start = time.perf_counter()
            logger.info("STT_START call_id=%s ts=%s",
                        job.call_id, datetime.now(timezone.utc).isoformat())
            response = await http_client.post(
                STT_SERVICE_URL,
                content=job.audio_pcm16_8k,
                headers={
                    "X-Enqueue-Time": str(enqueue_time),
                    "X-Language": job.primary_language if job.primary_language else "en"
                },
                timeout=10.0,
            )
            t_end = time.perf_counter()
            if response.status_code == 200:
                res_data = response.json()
                logger.info(
                    "STT_END call_id=%s ts=%s gateway_ms=%.2f "
                    "queue_wait_ms=%.2f preprocess_ms=%.2f inference_ms=%.2f "
                    "worker_pid=%s text='%s' confidence_proxy=%.4f avg_logprob=%s no_speech_prob=%s compression_ratio=%s audio_duration_ms=%s",
                    job.call_id, datetime.now(timezone.utc).isoformat(),
                    (t_end - t_start) * 1000.0,
                    res_data.get("queue_wait_ms", 0.0),
                    res_data.get("preprocess_ms", 0.0),
                    res_data.get("inference_ms", 0.0),
                    res_data.get("worker_pid", 0),
                    res_data["text"],
                    res_data["confidence"],
                    res_data.get("avg_logprob", "-"),
                    res_data.get("no_speech_prob", "-"),
                    res_data.get("compression_ratio", "-"),
                    res_data.get("audio_duration_ms", "-"),
                )
                result = STTResult(
                    call_id=job.call_id,
                    text=res_data["text"],
                    confidence=res_data["confidence"],
                    latency_ms=res_data["latency_ms"],
                )
            else:
                logger.error("STT_END_FAILED call_id=%s status=%s",
                             job.call_id, response.status_code)
                result = STTResult(call_id=job.call_id, text="", confidence=0.0, latency_ms=0.0)
            await results_queue.put(result)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("STT_END_ERROR call_id=%s error=%s", job.call_id, e)
            try:
                await results_queue.put(STTResult(call_id=job.call_id, text="", confidence=0.0, latency_ms=0.0))
            except Exception:
                pass


async def bridge_llm_queue(job_queue, results_queue, http_client):
    """Bridge for LLM requests: pulls LLMJob, calls LLM service, puts LLMResult."""
    while True:
        try:
            job = await job_queue.get()
            t_start = time.perf_counter()
            logger.info("LLM_START call_id=%s ts=%s",
                        job.call_id, datetime.now(timezone.utc).isoformat())

            escalation_str = job.escalation
            if hasattr(escalation_str, "value"):
                escalation_str = escalation_str.value
            if not escalation_str:
                escalation_str = "LOW"

            payload = {
                "job": {
                    "call_id": job.call_id,
                    "tenant_id": job.tenant_id,
                    "transcript": job.transcript,
                    "conversation_history": job.conversation_history,
                    "system_prompt": getattr(job, "system_prompt", None),
                },
                "escalation": escalation_str,
            }
            response = await http_client.post(
                LLM_SERVICE_URL, json=payload, timeout=12.0
            )
            t_end = time.perf_counter()
            if response.status_code == 200:
                res_data = response.json()
                logger.info(
                    "LLM_END call_id=%s ts=%s gateway_ms=%.2f "
                    "lock_wait_ms=%.2f inference_ms=%.2f first_token_ms=%.2f "
                    "reply='%s'",
                    job.call_id, datetime.now(timezone.utc).isoformat(),
                    (t_end - t_start) * 1000.0,
                    res_data.get("lock_wait_ms", 0.0),
                    res_data.get("inference_ms", 0.0),
                    res_data.get("first_token_ms", 0.0),
                    res_data["reply_text"],
                )
                result = LLMResult(
                    call_id=job.call_id,
                    reply_text=res_data["reply_text"],
                    escalation=res_data["escalation"],
                    latency_ms=res_data["latency_ms"],
                    first_token_ms=res_data["first_token_ms"],
                )
            else:
                logger.error("LLM_END_FAILED call_id=%s status=%s",
                             job.call_id, response.status_code)
                result = LLMResult(call_id=job.call_id, reply_text="I encountered a problem.",
                                   escalation="LOW", latency_ms=0.0)
            await results_queue.put(result)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("LLM_END_ERROR call_id=%s error=%s", job.call_id, e)
            try:
                await results_queue.put(LLMResult(call_id=job.call_id,
                                                   reply_text="Error.", escalation="LOW", latency_ms=0.0))
            except Exception:
                pass


async def bridge_tts_queue(job_queue, results_queue, http_client):
    """Bridge for TTS requests: pulls TTSJob, calls TTS service, puts TTSResult."""
    while True:
        try:
            job = await job_queue.get()
            enqueue_time = time.time()   # wall-clock for cross-process queue-wait
            t_start = time.perf_counter()
            logger.info("TTS_START call_id=%s ts=%s",
                        job.call_id, datetime.now(timezone.utc).isoformat())
            response = await http_client.post(
                TTS_SERVICE_URL,
                json={"text": job.text, "call_id": job.call_id, "enqueue_time": enqueue_time, "voice_model": job.voice_id},
                timeout=15.0,
            )
            t_end = time.perf_counter()
            if response.status_code == 200:
                audio_bytes = response.content
                logger.info(
                    "TTS_END call_id=%s ts=%s gateway_ms=%.2f "
                    "queue_wait_ms=%s inference_ms=%s bytes=%d",
                    job.call_id, datetime.now(timezone.utc).isoformat(),
                    (t_end - t_start) * 1000.0,
                    response.headers.get("X-Queue-Wait-MS", "?"),
                    response.headers.get("X-Inference-MS", "?"),
                    len(audio_bytes),
                )
                result = TTSResult(
                    call_id=job.call_id,
                    audio_pcm16_8k=audio_bytes,
                    latency_ms=float(response.headers.get("X-Latency-MS", "0.0")),
                )
            else:
                logger.error("TTS_END_FAILED call_id=%s status=%s",
                             job.call_id, response.status_code)
                result = TTSResult(call_id=job.call_id, audio_pcm16_8k=b'', latency_ms=0.0)
            await results_queue.put(result)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("TTS_END_ERROR call_id=%s error=%s", job.call_id, e)
            try:
                await results_queue.put(TTSResult(call_id=job.call_id, audio_pcm16_8k=b'', latency_ms=0.0))
            except Exception:
                pass

# ── AudioSocket & AMI Mappings ────────────────────────────────────────────────
from shared.ami import AMIClient, AMIException, AMIRegistry
from typing import Dict, Set

def _on_ami_new_channel(event: Dict[str, str]):
    channel = event.get("Channel")
    if channel:
        AMIRegistry.active_channels.add(channel)
        # Remember who is calling: this is where the real caller number comes from
        AMIRegistry.channel_info[channel] = {
            "caller": (event.get("CallerIDNum") or "").strip(),
            "caller_name": (event.get("CallerIDName") or "").strip(),
            "exten": (event.get("Exten") or "").strip(),
        }
        logger.debug("AMI: Tracked new active channel: %s (caller=%s)", channel, event.get("CallerIDNum"))

def _on_ami_new_callerid(event: Dict[str, str]):
    """Asterisk may fill in the caller ID after the channel is created."""
    channel = event.get("Channel")
    num = (event.get("CallerIDNum") or "").strip()
    if channel and num:
        info = AMIRegistry.channel_info.setdefault(channel, {"caller": "", "caller_name": "", "exten": ""})
        info["caller"] = num
        info["caller_name"] = (event.get("CallerIDName") or "").strip()

def _on_ami_var_set(event: Dict[str, str]):
    if event.get("Variable") == "AUDIO_UUID_VAR":
        channel = event.get("Channel")
        uuid_val = event.get("Value")
        if channel and uuid_val:
            uuid_val = uuid_val.lower()
            AMIRegistry.uuid_to_channel[uuid_val] = channel
            AMIRegistry.channel_to_uuid[channel] = uuid_val
            logger.info("AMI: Mapped UUID %s -> Channel %s", uuid_val, channel)

def _on_ami_hangup(event: Dict[str, str]):
    channel = event.get("Channel")
    if channel:
        AMIRegistry.active_channels.discard(channel)
        AMIRegistry.channel_info.pop(channel, None)
        uuid_val = AMIRegistry.channel_to_uuid.pop(channel, None)
        if uuid_val:
            AMIRegistry.uuid_to_channel.pop(uuid_val, None)
            logger.info("AMI: Cleaned mapping for Channel %s (UUID %s)", channel, uuid_val)
        logger.debug("AMI: Untracked hungup channel: %s", channel)

# ── Audio streaming & High-Precision Monotonic Pacer ─────────────────────────

FRAME_SIZE_BYTES = 320   # 160 samples @ 8kHz 16-bit PCM = 20ms per frame
FRAME_DURATION_S = 0.020  # 20ms
PREBUFFER_FRAMES = 3      # 60ms pre-buffer to prevent Asterisk jitter starvation

async def stream_audio_queue_to_asterisk(
    writer,
    audio_queue: asyncio.Queue,
    cancel_event: Optional[asyncio.Event] = None,
    call_id: str = "unknown",
    vad_engine: Optional[Any] = None,
):
    """
    High-precision monotonic pacer for AudioSocket streaming to Asterisk.
    Drains 320-byte (20ms) frames from audio_queue and paces them with
    clock drift compensation against time.monotonic().
    Feeds reference frames to vad_engine for echo cross-correlation rejection.
    """
    prebuffer = []
    while len(prebuffer) < PREBUFFER_FRAMES:
        if cancel_event and cancel_event.is_set():
            return
        try:
            chunk = await asyncio.wait_for(audio_queue.get(), timeout=10.0)
            if chunk is None:  # End-of-stream sentinel
                break
            prebuffer.append(chunk)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            break

    if not prebuffer:
        return

    t_stream_start = time.monotonic()
    next_deadline = t_stream_start
    sent_chunks = 0
    underrun_count = 0
    first_frame = True

    async def _send_frame(f_bytes: bytes) -> bool:
        nonlocal next_deadline, sent_chunks, underrun_count, first_frame
        if cancel_event and cancel_event.is_set():
            return False
        if len(f_bytes) < FRAME_SIZE_BYTES:
            f_bytes = f_bytes + b'\x00' * (FRAME_SIZE_BYTES - len(f_bytes))

        now = time.monotonic()
        sleep_dur = next_deadline - now
        if sleep_dur > 0.001:
            await asyncio.sleep(sleep_dur)
        elif sleep_dur < -0.050:
            underrun_count += 1
            next_deadline = time.monotonic()

        header = struct.pack('!BH', 0x10, len(f_bytes))
        try:
            writer.write(header + f_bytes)
            await writer.drain()
            if vad_engine:
                vad_engine.feed_agent_playback(f_bytes)
        except Exception:
            return False

        if first_frame:
            logger.info("PLAYBACK_START call_id=%s", call_id)
            first_frame = False

        sent_chunks += 1
        next_deadline += FRAME_DURATION_S
        return True

    for c in prebuffer:
        if not await _send_frame(c):
            return

    while True:
        if cancel_event and cancel_event.is_set():
            break
        try:
            chunk = await asyncio.wait_for(audio_queue.get(), timeout=10.0)
            if chunk is None:
                # Send 2 trailing comfort silence frames (40ms zero PCM) to cleanly ramp down DAC
                if not (cancel_event and cancel_event.is_set()):
                    await _send_frame(b'\x00' * FRAME_SIZE_BYTES)
                    await _send_frame(b'\x00' * FRAME_SIZE_BYTES)
                    logger.info("COMFORT_SILENCE_SENT call_id=%s frames=2 bytes=640", call_id)
                break
            if not await _send_frame(chunk):
                break
        except (asyncio.TimeoutError, asyncio.CancelledError):
            break

    elapsed_s = time.monotonic() - t_stream_start
    expected_s = sent_chunks * FRAME_DURATION_S
    avg_interval_ms = (elapsed_s / sent_chunks * 1000.0) if sent_chunks > 0 else 0.0
    logger.info(
        "PLAYBACK_END call_id=%s frames=%d audio_s=%.2f wall_s=%.2f underruns=%d",
        call_id, sent_chunks, expected_s, elapsed_s, underrun_count
    )
    if vad_engine:
        vad_engine.reset()

async def stream_audio_to_asterisk(writer, audio_pcm16_8k: bytes, cancel_event: Optional[asyncio.Event] = None, call_id: str = "unknown", vad_engine: Optional[Any] = None):
    """Adapter for static byte buffers (e.g. greeting). Chunks into 320B and paces."""
    q = asyncio.Queue()
    for i in range(0, len(audio_pcm16_8k), FRAME_SIZE_BYTES):
        q.put_nowait(audio_pcm16_8k[i:i+FRAME_SIZE_BYTES])
    q.put_nowait(None)
    await stream_audio_queue_to_asterisk(writer, q, cancel_event, call_id, vad_engine=vad_engine)

def split_script_into_chunks(text: str) -> list[str]:
    """Splits text or scripts into natural sentence/clause chunks (under 180 chars)
    so TTS synthesizes rapidly without hitting timeouts, streaming audio sub-second."""
    if not text or not text.strip():
        return []
    raw_parts = re.split(r'(?<=[.!?।\n])\s+', text.strip())
    chunks = []
    for p in raw_parts:
        p = p.strip()
        if not p:
            continue
        if len(p) > 200:
            sub_parts = re.split(r'(?<=[,;:])\s+', p)
            curr = ""
            for sp in sub_parts:
                if len(curr) + len(sp) < 180:
                    curr = f"{curr} {sp}" if curr else sp
                else:
                    if curr:
                        chunks.append(curr.strip())
                    curr = sp
            if curr:
                chunks.append(curr.strip())
        else:
            chunks.append(p)
    return chunks if chunks else [text.strip()]

# ── Call handler ──────────────────────────────────────────────────────────────

async def handle_audiosocket_connection(reader, writer):
    peer = writer.get_extra_info('peername')
    logger.info("New AudioSocket call connected from %s", peer)

    # ── Admission gate ────────────────────────────────────────────────────────
    if not await _try_admit(peer):
        try:
            writer.write(struct.pack('!BH', 0x00, 0))   # AudioSocket hangup
            await writer.drain()
        except Exception:
            pass
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass
        return

    try:
        # Parse session ID / UUID from initial packet
        try:
            header = await reader.readexactly(3)
        except (asyncio.IncompleteReadError, ConnectionResetError, OSError):
            logger.debug("AudioSocket TCP connection closed before header bytes (probe/disconnect peer=%s)", peer)
            return

        payload_type, payload_len = struct.unpack('!BH', header)

        if payload_type == 0x01:
            uuid_bytes = await reader.readexactly(payload_len)
            call_id = uuid_bytes.hex()
            # Convert hex string (32 chars) to standard hyphenated UUID format
            call_id = f"{call_id[0:8]}-{call_id[8:12]}-{call_id[12:16]}-{call_id[16:20]}-{call_id[20:32]}".lower()
        else:
            call_id = f"call_{int(time.time())}"
            if payload_len > 0:
                await reader.readexactly(payload_len)

        logger.info("Call session started with call_id=%s", call_id)

        # Verify mapping exists or can be recovered (supports both Asterisk PBX and Direct AudioSocket test runners)
        try:
            channel_name = await AMIRegistry.get_channel_by_uuid(call_id)
            logger.info("Gateway: Correlated call_id=%s to Asterisk Channel=%s", call_id, channel_name)
        except Exception as e:
            logger.warning("Gateway: No Asterisk AMI channel for call_id=%s (Running in Direct AudioSocket test mode): %s", call_id, e)
            channel_name = f"DIRECT/{call_id}"

        # CRM: record the call in the ONE database (voice_crm.db) with the REAL caller number.
        # (Previously the TCP peer address 127.0.0.1 was used, so every caller became the same fake contact.)
        crm_info = {}
        try:
            chan_info = AMIRegistry.channel_info.get(channel_name, {})
            caller_phone = chan_info.get("caller", "")
            if channel_name.startswith("DIRECT/"):
                caller_phone = os.environ.get("TEST_CALLER_NUMBER", caller_phone)  # test harness override
            # Vobiz delivers every call to extension 700, so the dialed number is configured, not read.
            called_did = os.environ.get("INBOUND_DID", "+918065354620")
            crm_info = await astart_call(
                call_id=call_id,
                from_number=caller_phone or "unknown",
                to_number=called_did,
                direction="inbound",
                provider="vobiz",
            )
            logger.info(
                "CRM_CALL_STARTED call_id=%s org=%s contact_id=%s resolved_by=%s caller=%s",
                call_id, crm_info.get("organization_slug"), crm_info.get("contact_id"),
                crm_info.get("resolved_by"), caller_phone or "unknown",
            )
        except Exception as crm_err:
            logger.error("CRM call start hook warning: %s", crm_err)

        # Per-session queues — intra-session backpressure only.
        # These do NOT gate global call admission: each incoming connection
        # gets its own fresh queue set regardless of system load.
        # Global call admission is enforced above via _try_admit().
        stt_queue = LocalAsyncQueue(maxsize=5)
        stt_results = LocalAsyncQueue(maxsize=5)
        llm_queue = LocalAsyncQueue(maxsize=5)
        llm_results = LocalAsyncQueue(maxsize=5)
        tts_queue = LocalAsyncQueue(maxsize=5)
        tts_results = LocalAsyncQueue(maxsize=5)

        # Fetch IncomingCallConfig from DB to get user-configured prompt, voice, and greeting
        config = None
        system_prompt = None
        voice_model = None
        call_direction = "inbound"
        call_mode = None
        user_script = ""
        user_prompt = ""
        user_voice = None
        greeting = None
        primary_lang = None
        try:
            from services.dashboard.app.database import SessionLocal
            from services.dashboard.app.models.crm import IncomingCallConfig, CallSession as CRMCallSession
            with SessionLocal() as db_s:
                db_session = db_s.query(CRMCallSession).filter(CRMCallSession.id == call_id).first()
                if db_session and db_session.direction:
                    call_direction = db_session.direction.lower()

                custom_cfg = db_session.custom_fields if (db_session and isinstance(db_session.custom_fields, dict)) else {}
                call_mode = custom_cfg.get("call_mode")
                user_script = custom_cfg.get("script_content", "").strip() if custom_cfg.get("script_content") else ""
                user_prompt = custom_cfg.get("system_prompt", "").strip() if custom_cfg.get("system_prompt") else ""
                user_voice = custom_cfg.get("voice_model")

                if call_direction == "outbound" and (user_script or user_prompt or call_mode):
                    # ── OUTBOUND MANUAL / SCRIPT CALL (Follow modal parameters strictly) ──
                    logger.info("AUDIOSOCKET_SESSION call_id=%s using custom outbound parameters: mode=%s voice=%s",
                                call_id, call_mode, user_voice)
                    voice_model = user_voice or "cartesia_hi_sonic"

                    if call_mode == "SCRIPT" or (user_script and not user_prompt):
                        system_prompt = f"SCRIPT_MODE:{user_script}"
                        greeting = user_script
                    else:
                        system_prompt = user_prompt if user_prompt else None
                        greeting = user_script if user_script else None
                else:
                    # ── INBOUND CALL (IncomingCallConfig PRESERVED 100%) ────────────────
                    if db_session and db_session.organization_id:
                        config = db_s.query(IncomingCallConfig).filter(IncomingCallConfig.organization_id == db_session.organization_id).first()
                    if not config:
                        # Fallback to first configured business if this session has no specific config
                        config = db_s.query(IncomingCallConfig).first()
                    
                    if config:
                        primary_lang = config.primary_language
                        import datetime
                        now_ist = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=5, minutes=30)))
                        current_time_str = now_ist.strftime("%I:%M %p, %A, %B %d, %Y")

                        # Compile the system prompt mimicking preview_configuration
                        compiled_prompt = f"SYSTEM INSTRUCTIONS\n\n"
                        compiled_prompt += f"CURRENT TIME & DATE: {current_time_str} (IST)\n"
                        compiled_prompt += f"IDENTITY: You are {config.ai_name}, acting as a {config.role_description or 'receptionist'}.\n"
                        if config.business_name:
                            compiled_prompt += f"BUSINESS: {config.business_name}\n{config.business_description or ''}\n"
                        if config.primary_objective:
                            compiled_prompt += f"PRIMARY OBJECTIVE: {config.primary_objective}\n"
                        if config.behavior_rules:
                            compiled_prompt += "RULES:\n- " + "\n- ".join(config.behavior_rules) + "\n"
                        if config.faq_knowledge_base:
                            compiled_prompt += f"KNOWLEDGE BASE:\n{config.faq_knowledge_base}\n"
                        if config.system_instructions:
                            compiled_prompt += f"ADVANCED INSTRUCTIONS:\n{config.system_instructions}\n"
                        
                        compiled_prompt += "\nCONVERSATION GUIDELINES:\n"
                        compiled_prompt += "1. Direct & Specific Answer: Answer the caller's specific statement or question directly and accurately. If they ask the time, state the current time. If they ask your name, state your name. If they ask for your address, state that you are an AI assistant. If they ask you to repeat numbers or words, repeat them accurately.\n"
                        compiled_prompt += "2. Anti-Repetition (CRITICAL): NEVER repeat greetings or introductions ('नमस्ते', 'हैलो', 'मैं अनन्या हूँ'). NEVER end your responses with canned repetitive phrases like 'आपकी क्या मदद कर सकती हूँ?' or 'बताइए आपकी क्या समस्या है?'. You are having a natural ongoing conversation.\n"
                        compiled_prompt += "3. Pacing: Keep your reply strictly to ONE natural, complete sentence (around 10 to 18 words). Never cut off into broken fragments.\n"
                        if config.primary_language == 'hi':
                            compiled_prompt += "4. Language: Reply STRICTLY in warm, conversational Hindi using Devanagari script. Never reply in English.\n"
                            compiled_prompt += "FEW-SHOT EXAMPLES:\n"
                            compiled_prompt += "User: अपना नाम फिर बता सकते हो आप?\nAI: जी, मेरा नाम अनन्या है।\n"
                            compiled_prompt += "User: अभी टाइम क्या हुआ है?\nAI: अभी समय " + now_ist.strftime("%I:%M %p") + " है।\n"
                            compiled_prompt += "User: नंबर रिपीट कर दो एक दो तीन चार।\nAI: जी, एक, दो, तीन, चार।\n"
                            compiled_prompt += "User: आपका अड्रेस क्या है?\nAI: मैं एक डिजिटल एआई असिस्टेंट हूँ, मेरा कोई भौतिक पता नहीं है।\n"
                        elif config.primary_language == 'marwadi':
                            compiled_prompt += "4. Language: Reply STRICTLY in authentic, fluent Marwadi (मारवाड़ी) using Devanagari script. Use Marwadi vocabulary (e.g., म्हारो, थांकी, अठे, कठे, सा).\n"
                            compiled_prompt += "FEW-SHOT EXAMPLES:\n"
                            compiled_prompt += "User: आप अपनों नाम बता होगे?\nAI: म्हारो नाम अनन्या है सा।\n"
                            compiled_prompt += "User: अभी काई टेम हुयो है?\nAI: अभी समय " + now_ist.strftime("%I:%M %p") + " हुयो है सा।\n"
                            compiled_prompt += "User: नंबर बोलो एक दो तीन चार।\nAI: जी सा, एक, दो, तीन, चार।\n"
                            compiled_prompt += "User: थे कठे रा हो?\nAI: मैं एक डिजिटल एआई हूँ, थांकी सेवा में हमेशा अठे ही हाजिर हूँ।\n"
                        else:
                            compiled_prompt += "4. Language: Reply in conversational English.\n"

                        system_prompt = compiled_prompt
                        voice_model = config.voice_id
                        greeting = config.greeting_message
                        
                        if not greeting:
                            if config.primary_language == 'hi':
                                greeting = f"नमस्ते! मैं {config.ai_name} हूँ। आज मैं आपकी कैसे मदद कर सकती हूँ?"
                            elif config.primary_language == 'marwadi':
                                greeting = f"खम्मा घणी! मैं {config.ai_name} हूँ। आज मैं थांकी काई मदद कर सकूँ हूँ?"
                            else:
                                greeting = f"Hello! I'm {config.ai_name}. How can I help you today?"

        except Exception as db_err:
            logger.error("Failed to load call configuration from DB: %s", db_err)

        session = CallSession(
            call_id=call_id,
            tenant_id="tenant_test",
            system_prompt=system_prompt,
            greeting=greeting,
            voice_model=voice_model,
            primary_language=primary_lang or (config.primary_language if config else None),
            call_direction=call_direction,
        )
        handler = CallSessionHandler(
            session=session,
            stt_queue=stt_queue,
            llm_queue=llm_queue,
            tts_queue=tts_queue,
            stt_results=stt_results,
            llm_results=llm_results,
            tts_results=tts_results,
        )

        async with httpx.AsyncClient() as http_client:
            stt_bridge = asyncio.create_task(bridge_stt_queue(stt_queue, stt_results, http_client))
            llm_bridge = asyncio.create_task(bridge_llm_queue(llm_queue, llm_results, http_client))
            tts_bridge = asyncio.create_task(bridge_tts_queue(tts_queue, tts_results, http_client))

            call_dir = getattr(session, "call_direction", "inbound")
            is_script = bool(session.system_prompt and session.system_prompt.startswith("SCRIPT_MODE:"))
            greeting_finished = False

            current_turn_task: Optional[asyncio.Task] = None
            playback_cancel_event = asyncio.Event()

            def cancel_current_turn(reason: str = "barge-in"):
                nonlocal current_turn_task, playback_cancel_event
                if is_script and not greeting_finished:
                    logger.info("SCRIPT_RECITE_PROTECTED: Ignoring turn cancellation reason='%s' call_id=%s", reason, call_id)
                    return
                if current_turn_task and not current_turn_task.done():
                    logger.info(
                        "BARGE_IN_TRIGGERED call_id=%s reason='%s' state=%s",
                        call_id, reason, session.state
                    )
                    playback_cancel_event.set()
                    current_turn_task.cancel()
                    handler.drain_queues()
                    session.state = CallState.LISTENING

            watchdog_task = None
            heartbeat_task = None

            try:
                # Start immediately in LISTENING state so microphone is active from frame 1
                session.state = CallState.LISTENING
                logger.info("CALL_CONNECTED call_id=%s state=CallState.LISTENING (Mic actively listening)", call_id)
                # Neural VAD & Endpointing Engine (Echo-Aware Gating & Noise Floor Tracking)
                vad_engine = SileroEndpointingEngine(
                    speech_threshold=0.45,
                    barge_in_threshold=0.55,
                    pre_roll_frames=25,          # 500ms continuous ring buffer
                    confirm_frames_needed=3,     # 60ms fast speech confirmation
                    hangover_frames_needed=20,   # 400ms natural conversational clause endpointing
                    barge_in_frames_needed=5,    # 100ms robust barge-in confirmation
                    min_utterance_frames=10,     # 200ms min utterance
                    max_utterance_frames=750,    # 15.0s max
                    echo_correlation_threshold=0.58,
                )

                last_interaction_time = time.time()
                reprompt_count = 0

                async def _inactivity_watchdog():
                    nonlocal last_interaction_time, reprompt_count, current_turn_task, playback_cancel_event
                    while True:
                        try:
                            await asyncio.sleep(1.0)
                            if session.state == CallState.LISTENING and (current_turn_task is None or current_turn_task.done()):
                                idle_time = time.time() - last_interaction_time
                                if idle_time > 25.0 and reprompt_count == 0:
                                    reprompt_count = 1
                                    last_interaction_time = time.time()
                                    logger.info("INACTIVITY_REPROMPT_TRIGGERED call_id=%s idle=%.1fs", call_id, idle_time)
                                    async def _reprompt():
                                        try:
                                            session.state = CallState.AI_SPEAKING
                                            reprompt_text = "Are you still there? Please let me know how I can assist you."
                                            tts_res = await handler._run_tts(reprompt_text)
                                            if tts_res and tts_res.audio_pcm16_8k and not playback_cancel_event.is_set():
                                                await stream_audio_to_asterisk(writer, tts_res.audio_pcm16_8k, playback_cancel_event, call_id, vad_engine=vad_engine)
                                        except Exception as ex:
                                            logger.error("Reprompt error: %s", ex)
                                        finally:
                                            last_interaction_time = time.time()
                                            if session.state == CallState.AI_SPEAKING:
                                                session.state = CallState.LISTENING
                                    current_turn_task = asyncio.create_task(_reprompt())
                        except asyncio.CancelledError:
                            break
                        except Exception:
                            pass

                watchdog_task = asyncio.create_task(_inactivity_watchdog())

                async def _heartbeat_loop():
                    """Tell the CRM this call is alive. Without it the dashboard reaper (which can only see
                    its own process) would mark the call 'completed' ~45s after it started."""
                    while True:
                        try:
                            await asyncio.sleep(5.0)
                            await aheartbeat_call(
                                call_id,
                                media_status="RECEIVING",
                                vad_state="SPEAKING" if session.state == CallState.AI_SPEAKING else "LISTENING",
                            )
                        except asyncio.CancelledError:
                            break
                        except Exception:
                            pass

                heartbeat_task = asyncio.create_task(_heartbeat_loop())

                total_rx_bytes = 0
                first_rx_frame = True
                greeting_played = False
                outbound_timer_task = None

                call_dir = getattr(session, "call_direction", "inbound")
                is_script = bool(session.system_prompt and session.system_prompt.startswith("SCRIPT_MODE:"))
                greeting_finished = False

                if is_script:
                    greeting_text = session.system_prompt[12:].strip()
                elif session.greeting:
                    greeting_text = session.greeting
                elif call_dir == "outbound" and user_prompt:
                    greeting_text = ""
                elif session.system_prompt and ("hindi" in session.system_prompt.lower() or bool(re.search(r'[\u0900-\u097F]', session.system_prompt))):
                    greeting_text = "नमस्ते! मैं आपकी क्या सहायता कर सकता हूँ?"
                else:
                    greeting_text = "नमस्ते! मैं अनन्या बोल रही हूँ। आज मैं आपकी क्या मदद कर सकती हूँ?" if session.primary_language in ('hi', 'marwadi') else "Hello! Great to connect with you. What is on your mind today?"

                # Set SUPERFONE_STATUS=SUCCESS via AMI if on an Asterisk channel
                if not channel_name.startswith("DIRECT/"):
                    try:
                        res = await ami_client.send_action("Setvar", {
                            "Channel": channel_name,
                            "Variable": "SUPERFONE_STATUS",
                            "Value": "SUCCESS"
                        })
                        if res.get("Response", "").lower() == "success":
                            logger.info("Gateway: Set SUPERFONE_STATUS=SUCCESS on channel %s", channel_name)
                        else:
                            logger.error("Failed to set SUPERFONE_STATUS=SUCCESS via AMI: %s", res.get("Message"))
                    except Exception as ex:
                        logger.error("Error setting SUPERFONE_STATUS=SUCCESS: %s", ex)

                while True:
                    hdr = await reader.readexactly(3)
                    p_type, p_len = struct.unpack('!BH', hdr)
                    payload = await reader.readexactly(p_len)

                    if p_type == 0x00:
                        logger.info("Hangup from Asterisk (call_id=%s, total_rx_bytes=%d)", call_id, total_rx_bytes)
                        if outbound_timer_task and not outbound_timer_task.done():
                            outbound_timer_task.cancel()
                        if current_turn_task and not current_turn_task.done():
                            current_turn_task.cancel()
                        break
                    elif p_type == 0x03:
                        dtmf_digit = payload.decode('ascii')
                        logger.info("call_id=%s [DTMF Received] digit=%s", call_id, dtmf_digit)
                        if dtmf_digit == '0':
                            logger.info("call_id=%s DTMF 0 detected. Triggering human handoff.", call_id)
                            if current_turn_task and not current_turn_task.done():
                                current_turn_task.cancel()
                            try:
                                await handler.request_handoff_via_dtmf()
                            except Exception as ex:
                                logger.error("DTMF Handoff failed for call_id=%s: %s", call_id, ex)
                            break
                        else:
                            logger.info("call_id=%s DTMF digit %s logged but not routed.", call_id, dtmf_digit)
                            continue
                    elif p_type == 0x10:
                        total_rx_bytes += len(payload)
                        if first_rx_frame:
                            logger.info("AUDIOSOCKET_CONNECTED call_id=%s direction=%s", call_id, call_dir)
                            logger.info("AUDIO_RX_START call_id=%s frame_bytes=%d", call_id, len(payload))
                            first_rx_frame = False

                            # Humanized Spoken Welcome Greeting (Sentence-by-Sentence Streaming)
                            async def _play_welcome_greeting(cancel_ev: asyncio.Event):
                                nonlocal last_interaction_time, reprompt_count, greeting_played, greeting_finished
                                try:
                                    greeting_played = True
                                    text_to_speak = greeting_text

                                    # In outbound custom prompt mode, derive a natural 1-sentence opening greeting
                                    if call_dir == "outbound" and not text_to_speak and user_prompt:
                                        try:
                                            async with httpx.AsyncClient(timeout=3.0) as quick_c:
                                                gen_res = await quick_c.post(
                                                    "http://127.0.0.1:9093/llm",
                                                    json={
                                                        "prompt": f"System prompt: {user_prompt}\n\nTask: Speak your opening greeting sentence to the person answering your outbound call. 1 short sentence, max 12 words. Do not use quotation marks or say 'Thank you for calling'.",
                                                        "max_tokens": 25,
                                                        "temperature": 0.3
                                                    }
                                                )
                                                if gen_res.status_code == 200:
                                                    text_to_speak = gen_res.json().get("text", "").strip()
                                        except Exception as ex:
                                            logger.warning("Could not generate prompt opening line: %s", ex)
                                        if not text_to_speak:
                                            text_to_speak = "Hello! I am calling regarding your inquiry."

                                    if text_to_speak:
                                        if not any(msg.get("content") == text_to_speak for msg in handler.conversation_history):
                                            handler._record_turn("assistant", text_to_speak)

                                        chunks = split_script_into_chunks(text_to_speak)
                                        session.state = CallState.AI_SPEAKING
                                        logger.info("GREETING_START call_id=%s chunks=%d mode=%s", call_id, len(chunks), "SCRIPT" if is_script else "NORMAL")

                                        for idx, chunk in enumerate(chunks):
                                            if cancel_ev.is_set() and not is_script:
                                                logger.info("GREETING_STOPPED_BY_CANCEL call_id=%s at chunk %d/%d", call_id, idx, len(chunks))
                                                break
                                            tts_res = await handler._run_tts(chunk)
                                            if tts_res and tts_res.audio_pcm16_8k:
                                                if cancel_ev.is_set() and not is_script:
                                                    break
                                                script_cancel = asyncio.Event() if is_script else cancel_ev
                                                await stream_audio_to_asterisk(writer, tts_res.audio_pcm16_8k, script_cancel, call_id, vad_engine=vad_engine)

                                        logger.info("GREETING_END call_id=%s", call_id)
                                except asyncio.CancelledError:
                                    logger.info("GREETING_CANCELLED (barge-in) call_id=%s", call_id)
                                except Exception as ex:
                                    logger.error("Error playing welcome greeting call_id=%s: %s", call_id, ex)
                                finally:
                                    greeting_finished = True
                                    last_interaction_time = time.time()
                                    reprompt_count = 0
                                    if session.state == CallState.AI_SPEAKING:
                                        session.state = CallState.LISTENING
                                    vad_engine.reset()

                            if call_dir == "outbound":
                                delay = 0.4 if is_script else 1.8
                                # Outbound Call: Callee answers phone. For script mode, recite after 0.4s.
                                # For interactive AI mode, wait up to 1.8s for callee salutation.
                                async def _outbound_greeting_timer():
                                    nonlocal greeting_played, current_turn_task, playback_cancel_event
                                    await asyncio.sleep(delay)
                                    if not is_script and (vad_engine.state != VADState.LISTENING or vad_engine.confirm_count > 0):
                                        logger.info("OUTBOUND_GREETING_SUPPRESSED (callee in speech) call_id=%s", call_id)
                                        greeting_played = True
                                        return
                                    if not greeting_played and (is_script or session.state == CallState.LISTENING) and (current_turn_task is None or current_turn_task.done()):
                                        logger.info("OUTBOUND_GREETING_TIMER_TRIGGERED (speaking %s) call_id=%s", "script" if is_script else "greeting", call_id)
                                        current_turn_task = asyncio.create_task(_play_welcome_greeting(playback_cancel_event))

                                outbound_timer_task = asyncio.create_task(_outbound_greeting_timer())
                            else:
                                current_turn_task = asyncio.create_task(_play_welcome_greeting(playback_cancel_event))

                        is_ai_speaking = (session.state == CallState.AI_SPEAKING)
                        event, full_utterance, prob = vad_engine.process_frame(payload, is_ai_speaking=is_ai_speaking)

                        if event == "BARGE_IN":
                            preroll_bytes = len(vad_engine.utterance_chunks) * 320
                            logger.info(
                                "BARGE_IN_TRIGGERED call_id=%s prob=%.2f preroll_bytes=%d telemetry=%s",
                                call_id, prob, preroll_bytes, vad_engine.last_telemetry
                            )
                            cancel_current_turn(reason="sustained caller speech during AI playback")
                        elif event == "BARGE_IN_CANDIDATE":
                            logger.debug(
                                "BARGE_IN_CANDIDATE call_id=%s prob=%.2f telemetry=%s",
                                call_id, prob, vad_engine.last_telemetry
                            )
                        elif event == "SPEECH_START":
                            logger.info("VAD_SPEECH_START call_id=%s prob=%.2f", call_id, prob)
                            # Never cancel greeting timer on SPEECH_START:
                            # In script mode, the script MUST recite unconditionally.
                            # In interactive mode, wait for SPEECH_END to verify real words,
                            # preventing cancellation caused by short electrical/pickup line noise.
                        elif event == "SPEECH_END" and full_utterance:
                            samples = np.frombuffer(full_utterance, dtype=np.int16)
                            rms_level = float(np.sqrt(np.mean(samples.astype(np.float64)**2))) if len(samples) > 0 else 0.0
                            peak_level = int(np.max(np.abs(samples))) if len(samples) > 0 else 0
                            duration_ms = (len(full_utterance) / 16.0)

                            # Windowed frame energy: calculate max RMS in 20ms (160 sample) windows
                            # to protect quiet words whose average RMS is diluted by trailing silence
                            max_frame_rms = 0.0
                            if len(samples) >= 160:
                                n_frames = len(samples) // 160
                                frame_rmses = [
                                    float(np.sqrt(np.mean(samples[i*160:(i+1)*160].astype(np.float64)**2)))
                                    for i in range(n_frames)
                                ]
                                max_frame_rms = max(frame_rmses) if frame_rmses else 0.0

                            logger.info(
                                "VAD_SPEECH_END call_id=%s audio_duration_ms=%.1f audio_bytes=%d trailing_silence_ms=400.0 peak_level=%d max_frame_rms=%.1f avg_rms=%.1f prob=%.2f",
                                call_id, duration_ms, len(full_utterance), peak_level, max_frame_rms, rms_level, prob
                            )
                            # Reject pure electrical noise / muted line clicks below sensitive telephony thresholds
                            if peak_level < 300 or (rms_level < 40.0 and max_frame_rms < 120.0):
                                logger.debug(
                                    "call_id=%s Discarding line noise frame (peak=%d, max_frame_rms=%.1f, avg_rms=%.1f)",
                                    call_id, peak_level, max_frame_rms, rms_level
                                )
                                continue

                            # If in script mode and the script hasn't finished reciting, keep reciting!
                            if is_script and not greeting_finished:
                                logger.info("SCRIPT_RECITE_PROTECTED call_id=%s: callee speech detected (%.1fms) but preserving active script recitation.", call_id, duration_ms)
                                continue

                            # For interactive outbound calls, cancel greeting timer now that verified speech has arrived
                            if not is_script:
                                if outbound_timer_task and not outbound_timer_task.done():
                                    logger.info("OUTBOUND_GREETING_CANCELLED (callee verified speech arrived first) call_id=%s", call_id)
                                    outbound_timer_task.cancel()
                                    greeting_played = True

                            last_interaction_time = time.time()
                            reprompt_count = 0

                            if current_turn_task and not current_turn_task.done():
                                cancel_current_turn(reason="new turn starting")

                            playback_cancel_event = asyncio.Event()

                            async def _run_turn(audio_data: bytes, cancel_ev: asyncio.Event):
                                nonlocal last_interaction_time
                                try:
                                    logger.info("AUDIO_DISPATCH_START call_id=%s bytes=%d", call_id, len(audio_data))
                                    await handler.handle_utterance_stream(
                                        audio_data,
                                        lambda item: stream_audio_queue_to_asterisk(writer, item, cancel_ev, call_id, vad_engine=vad_engine) if isinstance(item, asyncio.Queue) else stream_audio_to_asterisk(writer, item, cancel_ev, call_id),
                                        http_client,
                                        cancel_ev,
                                    )
                                    logger.info("AUDIO_DISPATCH_END call_id=%s", call_id)
                                except asyncio.CancelledError:
                                    logger.info("call_id=%s Turn execution cancelled (barge-in)", call_id)
                                    handler.drain_queues()
                                except CallFailedError as e:
                                    logger.error("Call turn failed call_id=%s: %s", call_id, e)
                                except Exception as e:
                                    logger.error("Unexpected error in turn task call_id=%s: %s", call_id, e, exc_info=True)
                                finally:
                                    last_interaction_time = time.time()
                                    if session.state in (CallState.AI_SPEAKING, CallState.PROCESSING_TTS, CallState.PROCESSING_LLM):
                                        session.state = CallState.LISTENING

                            current_turn_task = asyncio.create_task(_run_turn(full_utterance, playback_cancel_event))

            except asyncio.IncompleteReadError:
                logger.info("Call disconnected abruptly (call_id=%s)", call_id)
            except (ConnectionResetError, ConnectionAbortedError):
                logger.info("Call socket closed by peer (call_id=%s)", call_id)
            except Exception:
                logger.error("Error during call handling (call_id=%s):", call_id, exc_info=True)
            finally:
                if current_turn_task and not current_turn_task.done():
                    current_turn_task.cancel()
                stt_bridge.cancel()
                llm_bridge.cancel()
                tts_bridge.cancel()
                # Previously the watchdog was never cancelled and looped forever after every call
                for _bg_task in (watchdog_task, heartbeat_task):
                    if _bg_task is not None:
                        _bg_task.cancel()

    except Exception:
        logger.error("Error establishing call connection:", exc_info=True)
    finally:
        try:
            if 'handler' in locals() and handler:
                end_info = await aend_call(
                    call_id=call_id,
                    transcript_history=handler.conversation_history,
                    status="completed",
                    handoff_requested=getattr(handler, "handoff_requested", False),
                    handoff_reason=getattr(handler, "handoff_reason", None),
                )
                logger.info("CRM_CALL_ENDED call_id=%s result=%s", call_id, end_info)
        except Exception as crm_end_err:
            logger.error("CRM call end hook error: %s", crm_end_err)
        await _release_call()
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass
        logger.info("Call session finished. Connection closed. call_id=%s", locals().get("call_id", "unknown"))


async def main():
    global _active_calls_lock, ami_client
    _active_calls_lock = asyncio.Lock()

    # ── Connect AMI Client ───────────────────────────────────────────────────
    ami_secret = os.environ.get("ASTERISK_AMI_SECRET", "F-yfV4qLZt7-fnA5qzlq0_z6lH9HBUlc")
    if not ami_secret:
        logger.warning("ASTERISK_AMI_SECRET not configured. AMI client will be disabled.")

    ami_client = AMIClient(username="superfone", secret=ami_secret)
    AMIRegistry.client = ami_client
    ami_client.register_event_handler("Newchannel", _on_ami_new_channel)
    ami_client.register_event_handler("NewCallerid", _on_ami_new_callerid)
    ami_client.register_event_handler("VarSet", _on_ami_var_set)
    ami_client.register_event_handler("Hangup", _on_ami_hangup)

    try:
        await ami_client.connect()
        logger.info("Asterisk AMI connected successfully.")
    except Exception as e:
        logger.warning("Asterisk AMI connection failed (%s). Continuing AudioSocket gateway in standalone mode.", e)

    logger.info(
        "Admission limit: MAX_CONCURRENT_CALLS=%d (process-local)", MAX_CONCURRENT_CALLS
    )
    server = await asyncio.start_server(
        handle_audiosocket_connection, '0.0.0.0', 9092
    )
    addr = server.sockets[0].getsockname()
    logger.info("AudioSocket Gateway Server listening on %s", addr)
    async with server:
        await server.serve_forever()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Stopping Call Gateway.")

