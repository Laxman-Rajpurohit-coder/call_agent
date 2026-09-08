import os
import time
import asyncio
import json
import re
import aiohttp
from aiohttp import web
from llama_cpp import Llama

MODELS_DIR = r"c:\daily_works\superfone_call\models"
LLM_MODEL = os.path.join(MODELS_DIR, "qwen2.5-1.5b-instruct-q4_k_m.gguf")


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
        print(f"Loading LLM model once from {LLM_MODEL}...")
        self.llm = Llama(model_path=LLM_MODEL, n_ctx=2048, n_threads=8, n_batch=512, verbose=False)
        self.lock = asyncio.Lock()
        # Warmup pass to pre-allocate KV cache and JIT execution structures
        self.llm.create_chat_completion(
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=2,
            temperature=0.1
        )
        print("LLM model loaded and pre-warmed successfully.")

        app = web.Application()
        app.router.add_post('/llm', self.handle_llm)
        app.router.add_post('/llm/stream', self.handle_llm_stream)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, self.host, self.port)
        await site.start()
        print(f"LLM Server listening on http://{self.host}:{self.port}/llm and /llm/stream")

    async def handle_llm_stream(self, request):
        t_handler_start = time.perf_counter()

        data = await request.json()
        job_data = data.get("job", {})
        escalation_value = data.get("escalation", "HIGH")

        call_id = job_data.get("call_id")
        transcript = job_data.get("transcript", "")
        conversation_history = job_data.get("conversation_history", [])

        messages = [
            {"role": "system", "content": (
                "You are Pratham, a warm, genuine, and friendly AI representative of Mali Saini Samaj Seva Foundation (an NGO).\n"
                "GOAL & RESPONSIBILITIES:\n"
                "1. Donation Assistance: Help callers with donation inquiries, explain donation options (UPI, Netbanking, Cards), and confirm 80G tax exemption receipts.\n"
                "2. Conversational Style: Speak authentically and warmly like a friendly coordinator on a phone call. Keep replies to 1-2 natural spoken sentences (around 12-20 words, under 3 seconds of speech).\n"
                "3. Language Policy: Match the caller's language. If the caller speaks Hindi or Hinglish, respond strictly in warm conversational Hindi using Devanagari script (e.g. 'जी बिल्कुल, आप UPI या नेटबैंकिंग से डोनेशन दे सकते हैं और 80G टैक्स रसीद भी मिलेगी।'). If the caller speaks English, respond in clear warm English.\n"
                "4. Human Handoff: If the caller explicitly asks to speak to a person or manager, politely agree and say 'जी, मैं तुरंत आपकी कॉल हमारे मैनेजर से कनेक्ट कर रहा हूँ।'\n"
                "5. Direct & Helpful: Never say robotic phrases like 'How can I assist you today?' or repeat intro greetings."
            )}
        ]
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
        try:
            t_lock_start = time.perf_counter()
            async with self.lock:
                lock_wait_ms = (time.perf_counter() - t_lock_start) * 1000.0
                t_infer_start = time.perf_counter()
                producer_fut = loop.run_in_executor(None, producer, token_queue, loop)

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
            print(f"[LLM Server] Stream client disconnected early (call_id={call_id})")
        except Exception as e:
            print(f"[LLM Server] Stream Error: {e}")
            try:
                err_line = json.dumps({
                    "type": "sentence",
                    "text": "I am sorry, I encountered an issue.",
                    "first_token_ms": 0.0
                }) + "\n"
                await response.write(err_line.encode("utf-8"))
                await response.write_eof()
            except Exception:
                pass

        return response

    async def handle_llm(self, request):
        t_handler_start = time.perf_counter()

        data = await request.json()
        job_data = data.get("job", {})
        escalation_value = data.get("escalation", "HIGH")

        call_id = job_data.get("call_id")
        transcript = job_data.get("transcript", "")
        conversation_history = job_data.get("conversation_history", [])

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
            async with self.lock:
                lock_wait_ms = (time.perf_counter() - t_lock_wait_start) * 1000.0
                reply_text, inference_ms = await loop.run_in_executor(None, run_inference)
        except Exception as e:
            print(f"LLM Inference Error: {e}")
            reply_text = "I am sorry, I encountered an error."
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


if __name__ == '__main__':
    server = LLMServer()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(server.start())
        loop.run_forever()
    except KeyboardInterrupt:
        pass
