import os
import sys
from pathlib import Path

# Multi-Path .env Resolution (AGENTS.md Rule 4)
for env_candidate in (
    Path(__file__).resolve().parent / ".env",
    Path(__file__).resolve().parent.parent / ".env",
    Path(__file__).resolve().parents[2] / ".env",
    Path(r"c:\daily_works\superfone_call\.env"),
):
    if env_candidate.exists():
        try:
            with open(env_candidate, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and "=" in line and not line.startswith("#"):
                        k, v = line.split("=", 1)
                        k_clean = k.strip()
                        if k_clean not in os.environ:
                            os.environ[k_clean] = v.strip().strip('"').strip("'")
        except Exception:
            pass

import time
import asyncio
import json
import re
import logging
import aiohttp
from aiohttp import web
from typing import AsyncIterator, Optional
try:
    from llama_cpp import Llama
except ImportError:
    Llama = None

MODELS_DIR = r"c:\daily_works\superfone_call\models"
LLM_MODEL = os.path.join(MODELS_DIR, "qwen2.5-1.5b-instruct-q4_k_m.gguf")

# Shared with services/call_gateway/server.py and services/vobiz_bridge/server.py, so this
# process's own diagnostics (which model actually loaded, Groq errors) land in the one file
# already used for debugging a call, instead of being lost to stdout buffering (see below).
try:
    from services.dashboard.app.config import settings as _dashboard_settings
    _LOG_PATH = _dashboard_settings.CALL_GATEWAY_LOG
    os.makedirs(os.path.dirname(os.path.abspath(_LOG_PATH)), exist_ok=True)
    _formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(name)s - %(message)s")
    _file_handler = logging.FileHandler(_LOG_PATH, encoding="utf-8")
    _file_handler.setFormatter(_formatter)
    _console_handler = logging.StreamHandler()
    _console_handler.setFormatter(_formatter)
    logging.basicConfig(level=logging.INFO, handlers=[_file_handler, _console_handler])
except Exception:
    # If the dashboard package cannot be imported for some reason, fall back to plain console
    # logging rather than silently losing every message the way bare print() did before.
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")
logger = logging.getLogger("llm.server")

# Real-time conversational LLM used whenever no local GGUF model is loaded (see start()).
# Models are tried in order until one produces spoken text. Default to qwen/qwen3.8-27b per AGENTS.md Rule 3.
# Override with CONVERSATION_LLM_MODELS="model1,model2" in .env.
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODELS = [
    m.strip()
    for m in os.environ.get("CONVERSATION_LLM_MODELS", "qwen/qwen3.8-27b,openai/gpt-oss-20b").split(",")
    if m.strip()
]
GROQ_TEMPERATURE = float(os.environ.get("CONVERSATION_LLM_TEMPERATURE", "0.3"))
# Devanagari (Hindi) needs several tokens per word; 60 would cut a normal reply off mid-sentence.
GROQ_MAX_TOKENS = int(os.environ.get("CONVERSATION_LLM_MAX_TOKENS", "120"))

_http_session: Optional[aiohttp.ClientSession] = None


def _get_http() -> aiohttp.ClientSession:
    """One shared session, so consecutive turns reuse the TLS connection to Groq instead of
    paying a fresh handshake (~100+ ms) on every reply."""
    global _http_session
    if _http_session is None or _http_session.closed:
        _http_session = aiohttp.ClientSession(connector=aiohttp.TCPConnector(limit=100, ttl_dns_cache=300))
    return _http_session


class ThinkStripper:
    """Removes <think>...</think> reasoning from a token stream, even when a tag is split across
    chunks, so a reasoning model can never speak its own thinking aloud."""

    OPEN, CLOSE = "<think>", "</think>"

    def __init__(self):
        self._buf = ""
        self._in_think = False

    @staticmethod
    def _partial_suffix(s: str, tag: str) -> int:
        """Length of the longest proper prefix of `tag` that `s` ends with."""
        for n in range(min(len(tag) - 1, len(s)), 0, -1):
            if s.endswith(tag[:n]):
                return n
        return 0

    def feed(self, chunk: str) -> str:
        self._buf += chunk
        out = []
        while True:
            if self._in_think:
                i = self._buf.find(self.CLOSE)
                if i == -1:
                    keep = self._partial_suffix(self._buf, self.CLOSE)
                    self._buf = self._buf[len(self._buf) - keep:] if keep else ""
                    break
                self._buf = self._buf[i + len(self.CLOSE):]
                self._in_think = False
            else:
                i = self._buf.find(self.OPEN)
                if i == -1:
                    keep = self._partial_suffix(self._buf, self.OPEN)
                    cut = len(self._buf) - keep
                    out.append(self._buf[:cut])
                    self._buf = self._buf[cut:]
                    break
                out.append(self._buf[:i])
                self._buf = self._buf[i + len(self.OPEN):]
                self._in_think = True
        return "".join(out)

    def flush(self) -> str:
        """End of stream: text held back as a possible tag prefix was real text (unless mid-think)."""
        rest = "" if self._in_think else self._buf
        self._buf = ""
        return rest


_SSE_DONE = object()


def parse_sse_line(raw: bytes):
    """One line of Groq's server-sent-events stream -> text to speak ('' if nothing) or _SSE_DONE."""
    line = raw.decode("utf-8", "ignore").strip()
    if not line:
        return ""
    if "\n" in line:
        pieces = []
        for sub in line.split("\n"):
            p = parse_sse_line(sub.encode("utf-8"))
            if p is _SSE_DONE:
                return _SSE_DONE
            if p:
                pieces.append(p)
        return "".join(pieces)
    if not line.startswith("data:"):
        return ""
    body = line[5:].strip()
    if body == "[DONE]":
        return _SSE_DONE
    try:
        obj = json.loads(body)
    except json.JSONDecodeError:
        return ""
    if not isinstance(obj, dict):
        return ""
    choices = obj.get("choices") or []
    if not choices or not isinstance(choices[0], dict):
        return ""
    return (choices[0].get("delta") or {}).get("content") or ""


async def _groq_chat_stream(messages: list, max_tokens: Optional[int] = None) -> AsyncIterator[str]:
    """Yields the spoken text of a Groq streaming chat completion, chunk by chunk.

    Tries each model in GROQ_MODELS in order until one produces spoken text. Once any text has been
    yielded the reply is committed: a later failure keeps the partial reply and NEVER restarts with
    another model (that would splice two different answers together on the phone). If every model
    fails before producing anything, the last error is raised (the caller has an apology fallback).
    """
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is not set and no local GGUF model is loaded")
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    http = _get_http()
    last_error: Optional[Exception] = None
    for model in GROQ_MODELS:
        spoke = False
        stripper = ThinkStripper()
        t0 = time.perf_counter()
        try:
            payload = {
                "model": model,
                "messages": messages,
                "temperature": GROQ_TEMPERATURE,
                "max_tokens": max_tokens or GROQ_MAX_TOKENS,
                "presence_penalty": 0.6,
                "frequency_penalty": 0.6,
                "stream": True,
            }
            async with http.post(GROQ_URL, headers=headers, json=payload,
                                 timeout=aiohttp.ClientTimeout(total=20, connect=5)) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    last_error = RuntimeError(f"Groq {model} returned HTTP {resp.status}: {body[:200]}")
                    logger.warning("Conversation LLM: %s", last_error)
                    continue
                while True:
                    raw_line = await resp.content.readline()
                    if not raw_line:
                        break
                    piece = parse_sse_line(raw_line)
                    if piece is _SSE_DONE:
                        break
                    if not piece:
                        continue
                    text = stripper.feed(piece)
                    if text:
                        if not spoke:
                            logger.info("Conversation LLM: model=%s first_token_ms=%.0f",
                                        model, (time.perf_counter() - t0) * 1000.0)
                        spoke = True
                        yield text
                tail = stripper.flush()
                if tail:
                    spoke = True
                    yield tail
            if spoke:
                return
            last_error = RuntimeError(f"Groq {model} produced no spoken text")
            logger.warning("Conversation LLM: %s", last_error)
        except Exception as ex:
            if spoke:
                logger.warning("Conversation LLM: model %s failed mid-reply (%s); keeping the partial reply", model, ex)
                return
            last_error = ex
            logger.warning("Conversation LLM: model %s failed: %s", model, ex)
    raise last_error or RuntimeError("All Groq models failed")


async def _drain_groq_into_queue(q: asyncio.Queue, messages: list, first_token_ms_holder: list, t_infer: float) -> None:
    """Adapter so handle_llm_stream's existing sentence-buffering consumer loop (built for the
    thread-based local-model producer) works identically when the source is this async generator.
    Runs on the event loop itself (not a thread), so plain `await q.put(...)` is safe here -
    the local-model producer instead needs call_soon_threadsafe because it runs in a worker thread.
    """
    try:
        async for text in _groq_chat_stream(messages):
            if first_token_ms_holder[0] is None:
                first_token_ms_holder[0] = (time.perf_counter() - t_infer) * 1000.0
            await q.put(text)
    except Exception as ex:
        await q.put(ex)
    finally:
        await q.put(None)


async def warm_up_groq() -> bool:
    """Startup self-test: a bad key or model id shows in the log immediately, not on the first call."""
    t0 = time.perf_counter()
    try:
        async for _ in _groq_chat_stream([{"role": "user", "content": "Say hi in one word."}], max_tokens=8):
            break
        logger.info("Conversation LLM warm-up OK in %.0f ms (models, in order: %s)",
                    (time.perf_counter() - t0) * 1000.0, ", ".join(GROQ_MODELS))
        return True
    except Exception as ex:
        logger.error("Conversation LLM warm-up FAILED: %s - live calls will only get the apology "
                     "fallback until this is fixed", ex)
        return False


class _NoLock:
    """Stand-in for the inference lock on the Groq path. The lock exists to stop concurrent llama.cpp
    calls corrupting memory; Groq is network I/O, and holding a global lock across it would make
    every concurrent caller wait in a single-file queue for no reason."""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


async def _groq_collect(messages: list, max_tokens: Optional[int] = None) -> str:
    """Whole reply as one string (for the non-streaming endpoints)."""
    return "".join([t async for t in _groq_chat_stream(messages, max_tokens)]).strip()


ABBREVIATIONS = {
    'mr.', 'mrs.', 'ms.', 'dr.', 'prof.', 'sr.', 'jr.', 'rs.', 'e.g.', 'i.e.', 'vs.', 'etc.',
    'approx.', 'no.', 'st.', 'pin.', 'dist.', 'raj.', 'co.', 'ltd.', 'inc.'
}

OPENERS = {'certainly', 'sure', 'yes', 'no', 'hello', 'namaste', 'नमस्ते', 'बिल्कुल', 'जी', 'good', 'धन्यवाद'}

def extract_sentences(buffer: str, min_words: int = 3):
    sentences = []
    # Split ONLY on terminal punctuation (. ? ! ।) followed by whitespace or end-of-string.
    # Never split on newlines, colons, or commas which chop spoken speech into broken clauses.
    pattern = re.compile(r'([.?!।]+(?:\s+|$))')
    last_idx = 0
    for match in pattern.finditer(buffer):
        end_idx = match.end()
        candidate = buffer[last_idx:end_idx].strip()
        tokens = candidate.split()
        if tokens:
            last_word = tokens[-1].lower().rstrip('?!,;:।—')
            # Protect abbreviations, initials, isolated digits, or colons
            if (last_word in ABBREVIATIONS or 
                re.search(r'\d+\.\s*$', candidate) or 
                re.search(r'\b[A-Za-z]\.\s*$', candidate) or
                re.search(r'[\d:,]\s*$', candidate)):
                continue
            # Conversational openers (< min_words) can be yielded early for instant auditory acknowledgment
            if len(tokens) < min_words:
                first_clean = tokens[0].lower().rstrip('?!,;:।')
                if not (len(tokens) >= 2 and first_clean in OPENERS):
                    continue
        if len(candidate) < 3:
            continue
        sentences.append(candidate)
        last_idx = end_idx
    return sentences, buffer[last_idx:]


class LLMServer:
    """
    LLM Server. Inference is fully serialized system-wide via asyncio.Lock to
    prevent concurrent llama.cpp memory corruption. This creates a hard
    throughput ceiling of one inference at a time — the primary capacity
    constraint until a multi-instance or batching server is introduced.

    Timing boundaries returned per request:
      lock_wait_ms  — time blocked on asyncio.Lock (other callers ahead in queue)
      inference_ms  — time inside create_chat_completion() only (measured directly)
      first_token_ms — time to first token within inference
      latency_ms    — total HTTP handler time (includes JSON parse, prompt build,
                       lock wait, inference, response serialization)

    lock_wait_ms + inference_ms < latency_ms; the remainder is HTTP/scheduling
    overhead and is expected.
    """

    def __init__(self, host="127.0.0.1", port=9093):
        self.host = host
        self.port = port
        self.llm = None
        self.lock = None

    async def start(self):
        self.lock = asyncio.Lock()
        # Strict 3-API rule: Pure Groq Cloud inference (no local GGUF memory footprint or CPU stall)
        self.llm = None
        if not os.environ.get("GROQ_API_KEY"):
            logger.error("GROQ_API_KEY is not set: every reply will be the apology fallback")
        else:
            logger.info("Conversation LLM active mode: Groq Cloud API (models in order: %s)", ", ".join(GROQ_MODELS))
            self._warmup_task = asyncio.create_task(warm_up_groq())

        app = web.Application()
        app.router.add_post('/llm', self.handle_llm)
        app.router.add_post('/llm/stream', self.handle_llm_stream)
        app.router.add_post('/v1/chat/completions', self.handle_openai_chat)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, self.host, self.port)
        await site.start()
        logger.info("LLM Server listening on http://%s:%s/llm/stream, /llm and /v1/chat/completions", self.host, self.port)

    async def handle_llm_stream(self, request):
        t_handler_start = time.perf_counter()

        data = await request.json()
        job_data = data.get("job", {})
        escalation_value = data.get("escalation", "HIGH")

        call_id = job_data.get("call_id")
        transcript = job_data.get("transcript", "")
        conversation_history = job_data.get("conversation_history", [])
        system_prompt = job_data.get("system_prompt")

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        else:
            messages.append({"role": "system", "content": (
                "You are a warm, genuine, and friendly human conversational companion on a live phone call.\n"
                "CONVERSATION GUIDELINES:\n"
                "1. Warm & Natural: Speak authentically like a real friend on a phone call. Use natural spoken conversational markers when appropriate (e.g. 'Oh absolutely!', 'Definitely,', 'Honestly, I think...', 'That sounds wonderful!', 'हाँ बिलकुल,', 'जी हाँ बिलकुल,', 'सच कहूँ तो,', 'यह बहुत बढ़िया है!').\n"
                "2. Pacing: Keep your reply strictly to ONE natural, complete sentence (around 12 to 18 words, under 2.5 seconds of speech). Never ramble, and never cut off into broken fragments.\n"
                "3. Language Matching: Detect the user's language (Hindi or English or Hinglish). If Hindi/Hinglish, reply strictly in warm, conversational Hindi using Devanagari script (e.g. 'हाँ बिलकुल! आप हमारे सुरक्षित पोर्टल से डोनेशन दे सकते हैं, धन्यवाद!'). Never output robotic refusal phrases.\n"
                "4. Direct Answer: Answer the caller's thought directly. Never say robotic phrases like 'How can I assist you today?' or repeat introductions."
            )})

        # Keep last 6 turns of history for conversation continuity
        for msg in conversation_history[-6:]:
            messages.append({"role": msg["role"], "content": msg["content"]})
        messages.append({"role": "user", "content": transcript})

        response = web.StreamResponse(
            status=200,
            headers={'Content-Type': 'application/x-ndjson'}
        )
        await response.prepare(request)

        loop = asyncio.get_running_loop()
        token_queue = asyncio.Queue()
        first_token_ms_holder = [None]

        def producer(q, loop_ref):
            t_infer = time.perf_counter()
            try:
                stream = self.llm.create_chat_completion(
                    messages=messages,
                    max_tokens=35,
                    temperature=0.35,
                    repeat_penalty=1.15,
                    stream=True,
                )
                for chunk in stream:
                    if first_token_ms_holder[0] is None:
                        first_token_ms_holder[0] = (time.perf_counter() - t_infer) * 1000.0
                    choices = chunk.get("choices", [])
                    if choices:
                        delta = choices[0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            loop_ref.call_soon_threadsafe(q.put_nowait, content)
            except Exception as e:
                loop_ref.call_soon_threadsafe(q.put_nowait, e)
            finally:
                loop_ref.call_soon_threadsafe(q.put_nowait, None)

        lock_wait_ms = 0.0
        producer_fut = None
        # Local llama.cpp must run one inference at a time; Groq (network I/O) must not be serialized.
        inference_lock = self.lock if self.llm is not None else _NoLock()
        try:
            t_lock_start = time.perf_counter()
            async with inference_lock:
                lock_wait_ms = (time.perf_counter() - t_lock_start) * 1000.0
                t_infer_start = time.perf_counter()
                if self.llm is not None:
                    producer_fut = loop.run_in_executor(None, producer, token_queue, loop)
                else:
                    producer_fut = asyncio.create_task(
                        _drain_groq_into_queue(token_queue, messages, first_token_ms_holder, t_infer_start))

                buffer = ""
                full_reply = []

                while True:
                    item = await token_queue.get()
                    if item is None:
                        break
                    if isinstance(item, Exception):
                        raise item

                    buffer += item
                    full_reply.append(item)

                    sentences, remaining = extract_sentences(buffer)
                    if sentences:
                        for s in sentences:
                            msg_line = json.dumps({
                                "type": "sentence",
                                "text": s,
                                "first_token_ms": round(first_token_ms_holder[0] or 0.0, 2),
                            }) + "\n"
                            await response.write(msg_line.encode("utf-8"))
                        buffer = remaining

                # If there is remaining text in the buffer, yield it as final sentence
                if buffer.strip():
                    msg_line = json.dumps({
                        "type": "sentence",
                        "text": buffer.strip(),
                        "first_token_ms": round(first_token_ms_holder[0] or 0.0, 2),
                    }) + "\n"
                    await response.write(msg_line.encode("utf-8"))

                await producer_fut
                inference_ms = (time.perf_counter() - t_infer_start) * 1000.0
                latency_ms = (time.perf_counter() - t_handler_start) * 1000.0

                done_line = json.dumps({
                    "type": "done",
                    "full_text": "".join(full_reply).strip(),
                    "call_id": call_id,
                    "escalation": escalation_value,
                    "latency_ms": round(latency_ms, 2),
                    "inference_ms": round(inference_ms, 2),
                    "lock_wait_ms": round(lock_wait_ms, 2),
                    "first_token_ms": round(first_token_ms_holder[0] or 0.0, 2),
                }) + "\n"
                await response.write(done_line.encode("utf-8"))
                await response.write_eof()
        except (ConnectionResetError, asyncio.CancelledError, aiohttp.ClientConnectionResetError):
            logger.info("Stream client disconnected early (call_id=%s)", call_id)
        except Exception as e:
            logger.error("Stream error (call_id=%s): %r", call_id, e)
            try:
                is_hindi = bool(re.search(r'[\u0900-\u097F]', system_prompt or "")) or "hindi" in (system_prompt or "").lower() or "marwadi" in (system_prompt or "").lower()
                err_text = "माफ़ कीजिएगा, मैं समझ नहीं पाई। कृपया दोबारा कहिए।" if is_hindi else "I am sorry, I encountered an issue."
                err_line = json.dumps({
                    "type": "sentence",
                    "text": err_text,
                    "first_token_ms": 0.0
                }) + "\n"
                await response.write(err_line.encode("utf-8"))
                await response.write_eof()
            except Exception:
                pass
        finally:
            # Caller hung up (or something failed): stop the Groq request instead of letting it run on.
            if isinstance(producer_fut, asyncio.Task) and not producer_fut.done():
                producer_fut.cancel()

        return response

    async def handle_llm(self, request):
        t_handler_start = time.perf_counter()

        data = await request.json()
        job_data = data.get("job", {})
        escalation_value = data.get("escalation", "HIGH")

        call_id = job_data.get("call_id")
        transcript = job_data.get("transcript", "")
        conversation_history = job_data.get("conversation_history", [])
        system_prompt = job_data.get("system_prompt")

        if system_prompt:
            messages = [{"role": "system", "content": system_prompt}]
        else:
            messages = [
                {"role": "system", "content": (
                    "You are a warm, genuine, and friendly human conversational companion on a live phone call.\n"
                    "CONVERSATION GUIDELINES:\n"
                    "1. Warm & Natural: Speak authentically like a real friend on a phone call. Use natural spoken conversational markers when appropriate (e.g. 'Oh absolutely!', 'Definitely,', 'Honestly, I think...', 'That sounds wonderful!', 'अरे वाह,', 'हाँ बिल्कुल,', 'सच में,', 'बहुत बढ़िया!').\n"
                    "2. Pacing: Keep your reply strictly to ONE natural, complete sentence (around 12 to 18 words, under 2.5 seconds of speech). Never ramble, and never cut off into broken fragments.\n"
                    "3. Language Matching: Detect the user's language (Hindi or English or Hinglish). If Hindi/Hinglish, reply strictly in warm, conversational Hindi using Devanagari script (e.g. 'अरे वाह! आपसे बात करके बहुत खुशी हुई, धन्यवाद!'). Never output robotic refusal phrases.\n"
                    "4. Direct Answer: Answer the caller's thought directly. Never say robotic phrases like 'How can I assist you today?' or repeat introductions."
                )}
            ]
        for msg in conversation_history[-6:]:
            messages.append({"role": msg["role"], "content": msg["content"]})
        messages.append({"role": "user", "content": transcript})

        loop = asyncio.get_running_loop()
        first_token_ms_holder = [None]

        def run_inference():
            """
            Runs in the default executor (thread pool) inside the asyncio.Lock.
            inference_ms is measured directly here — it covers only the
            create_chat_completion() call, not JSON parsing or lock wait.
            """
            t_infer = time.perf_counter()
            stream = self.llm.create_chat_completion(
                messages=messages,
                max_tokens=35,
                temperature=0.35,
                repeat_penalty=1.15,
                stream=True,
            )
            reply_parts = []
            for chunk in stream:
                if first_token_ms_holder[0] is None:
                    first_token_ms_holder[0] = (time.perf_counter() - t_infer) * 1000.0
                choices = chunk.get("choices", [])
                if choices:
                    delta = choices[0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        reply_parts.append(content)
            inference_ms = (time.perf_counter() - t_infer) * 1000.0
            return "".join(reply_parts).strip(), inference_ms

        lock_wait_ms = 0.0
        inference_ms = 0.0
        reply_text = ""
        try:
            t_lock_wait_start = time.perf_counter()
            inference_lock = self.lock if self.llm is not None else _NoLock()
            async with inference_lock:
                lock_wait_ms = (time.perf_counter() - t_lock_wait_start) * 1000.0
                if self.llm is not None:
                    reply_text, inference_ms = await loop.run_in_executor(None, run_inference)
                else:
                    t_groq = time.perf_counter()
                    reply_text = await _groq_collect(messages)
                    inference_ms = (time.perf_counter() - t_groq) * 1000.0
                    first_token_ms_holder[0] = inference_ms
        except Exception as e:
            logger.error("LLM inference error: %r", e)
            is_hindi = bool(re.search(r'[\u0900-\u097F]', system_prompt or "")) or "hindi" in (system_prompt or "").lower() or "marwadi" in (system_prompt or "").lower()
            reply_text = "माफ़ कीजिएगा, मैं समझ नहीं पाई। कृपया दोबारा कहिए।" if is_hindi else "I am sorry, I encountered an error."
            first_token_ms_holder[0] = 0.0

        latency_ms = (time.perf_counter() - t_handler_start) * 1000.0

        return web.json_response({
            "call_id": call_id,
            "reply_text": reply_text,
            "escalation": escalation_value,
            "latency_ms": round(latency_ms, 3),
            "first_token_ms": round(first_token_ms_holder[0] or latency_ms, 3),
            "lock_wait_ms": round(lock_wait_ms, 3),
            "inference_ms": round(inference_ms, 3),
        })

    async def handle_openai_chat(self, request):
        t_handler_start = time.perf_counter()
        data = await request.json()
        messages = data.get("messages", [])

        if not messages:
            messages = [{"role": "user", "content": "Hello"}]

        loop = asyncio.get_running_loop()

        def run_inference():
            t0 = time.perf_counter()
            resp = self.llm.create_chat_completion(
                messages=messages,
                max_tokens=60,
                temperature=0.7
            )
            dur = (time.perf_counter() - t0) * 1000.0
            content = resp["choices"][0]["message"]["content"].strip()
            return content, dur

        if self.llm is not None:
            async with self.lock:
                reply_content, inference_ms = await loop.run_in_executor(None, run_inference)
        else:
            t_groq = time.perf_counter()
            reply_content = await _groq_collect(messages, max_tokens=60)
            inference_ms = (time.perf_counter() - t_groq) * 1000.0

        latency_ms = (time.perf_counter() - t_handler_start) * 1000.0

        return web.json_response({
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": reply_content
                }
            }],
            "latency_ms": round(latency_ms, 2),
            "inference_ms": round(inference_ms, 2)
        })


if __name__ == '__main__':
    server = LLMServer()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(server.start())
        loop.run_forever()
    except KeyboardInterrupt:
        pass
