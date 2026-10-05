"""
One CallSessionHandler instance = one lightweight async task per call.
It holds no AI model references — it only moves jobs into queues and
awaits results, so N concurrent calls means N cheap asyncio tasks, not
N copies of Whisper/Qwen/Piper in memory.
"""

import asyncio
import logging
import json
import re
import time
from typing import Optional

from shared.protocol import (
    CallEvent,
    CallSession,
    CallState,
    EscalationLevel,
    LLMJob,
    LLMResult,
    STTJob,
    STTResult,
    TTSJob,
    TTSResult,
    TRANSFERABLE_STATES,
)
from shared.queue.interface import JobQueue, QueueFullError

logger = logging.getLogger("call_gateway.session")

# Per-stage timeouts derived from M1 capacity model (Phase 2).
# LLM is fully serialized (one asyncio.Lock system-wide); 8.5 s is a
# conservative worst-case bound for 5 simultaneous callers with peak
# CPU contention. STT pool runs parallel Whisper inference; under 5-call
# concurrent load the worst observed latency was 2508 ms, so 4.0 s gives
# ~1.5 s headroom. TTS uses the persistent warm Piper pool (<300 ms
# observed); 3.0 s covers scheduling spikes.
STT_TIMEOUT_S = 8.0
LLM_TIMEOUT_S = 8.5
TTS_TIMEOUT_S = 12.0


class CallFailedError(Exception):
    pass


class CallSessionHandler:
    def __init__(
        self,
        session: CallSession,
        stt_queue: JobQueue,
        stt_results: JobQueue,
        llm_queue: JobQueue,
        llm_results: JobQueue,
        tts_queue: JobQueue,
        tts_results: JobQueue,
    ) -> None:
        self.session = session
        self.stt_queue = stt_queue
        self.stt_results = stt_results
        self.llm_queue = llm_queue
        self.llm_results = llm_results
        self.tts_queue = tts_queue
        self.tts_results = tts_results
        self.conversation_history = []
        # Set when a human handoff is requested (DTMF 0, low confidence, ...); saved to the CRM at hangup
        self.handoff_requested = False
        self.handoff_reason: Optional[str] = None

    def _record_turn(self, role: str, text: str) -> None:
        """Append a turn to the transcript AND emit the log line the dashboard live-monitor parses
        (USER_UTTERANCE / AI_RESPONSE). Empty text is ignored."""
        text = " ".join(str(text or "").split())  # one line: newlines would break the log parser
        if not text:
            return
        self.conversation_history.append({"role": role, "content": text})
        tag = "USER_UTTERANCE" if role == "user" else "AI_RESPONSE"
        logger.info("%s call_id='%s' text='%s'", tag, self.session.call_id, text)
    def _set_state(self, new_state: CallState) -> None:
        old_state = self.session.state
        self.session.state = new_state
        logger.info(
            "STATE_CHANGE call_id=%s old=%s new=%s",
            self.session.call_id, old_state, new_state,
        )

    def drain_queues(self) -> None:
        """Purge any pending jobs or results across all queues for this session."""
        for q in (self.stt_queue, self.stt_results, self.llm_queue, self.llm_results, self.tts_queue, self.tts_results):
            if hasattr(q, "_queue"):
                while not q._queue.empty():
                    try:
                        q._queue.get_nowait()
                    except (asyncio.QueueEmpty, ValueError):
                        break

    async def handle_utterance_stream(
        self,
        audio_pcm16_8k: bytes,
        audio_stream_callback,
        http_client,
        cancel_event: Optional[asyncio.Event] = None,
    ) -> None:
        """One streaming turn: audio in -> STT -> streaming LLM sentences -> TTS -> audio stream callback."""
        if cancel_event and cancel_event.is_set():
            return

        t_turn_start = time.perf_counter()
        self._set_state(CallState.PROCESSING_STT)
        logger.info("STT_START call_id=%s", self.session.call_id)
        t_stt_start = time.perf_counter()
        stt_result = await self._run_stt(audio_pcm16_8k)
        stt_latency_ms = (time.perf_counter() - t_stt_start) * 1000.0

        if cancel_event and cancel_event.is_set():
            return

        if stt_result is None or not stt_result.text or not stt_result.text.strip():
            logger.info("STT_END call_id=%s transcript='' latency_ms=%.1f (silence/non-speech)", self.session.call_id, stt_latency_ms)
            self._set_state(CallState.LISTENING)
            return

        # N-gram repetition guard: reject runaway hallucination loops before reaching LLM
        words = re.findall(r"[a-zA-Z0-9']+", stt_result.text.lower())
        is_repetitive = False
        rep_phrase = ""
        rep_count = 0
        if len(words) >= 6:
            for phrase_size in range(1, 6):
                for i in range(len(words) - phrase_size * 3 + 1):
                    phrase = words[i:i + phrase_size]
                    if words[i:i + phrase_size * 3] == phrase * 3:
                        k = 0
                        while i + (k + 1) * phrase_size <= len(words) and words[i + k * phrase_size:i + (k + 1) * phrase_size] == phrase:
                            k += 1
                        is_repetitive = True
                        rep_phrase = " ".join(phrase)
                        rep_count = k
                        break
                if is_repetitive:
                    break

        if is_repetitive:
            logger.warning(
                "STT_REJECTED call_id=%s reason=repetition word_count=%d repeated_phrase='%s' repeat_count=%d",
                self.session.call_id, len(words), rep_phrase, rep_count
            )
            self._set_state(CallState.LISTENING)
            return

        logger.info("STT_END call_id=%s transcript='%s' latency_ms=%.1f", self.session.call_id, stt_result.text, stt_latency_ms)

        # Record the caller's words NOW, not after the AI finishes: if the caller barges in and this turn is
        # cancelled, their words must still reach the transcript. The LLM server appends the current
        # utterance itself, so it is given the history as it was BEFORE this turn (no duplicate message).
        history_before_turn = list(self.conversation_history)
        self._record_turn("user", stt_result.text)
        from shared.escalation import classify
        escalation = classify(stt_result.text, stt_result.confidence)

        if escalation == EscalationLevel.LOW:
            from shared.ami import AMIRegistry
            if AMIRegistry.client and AMIRegistry.client.is_connected:
                try:
                    await self._request_handoff("user requested human agent")
                    return
                except Exception as ex:
                    logger.warning("call_id=%s Handoff failed (%s), continuing with LLM turn", self.session.call_id, ex)
            else:
                logger.info("call_id=%s Human handoff requested but AMI client not connected (Vobiz direct call). Continuing with LLM turn.", self.session.call_id)

        if cancel_event and cancel_event.is_set():
            return

        self._set_state(CallState.PROCESSING_LLM)
        logger.info("LLM_START call_id=%s transcript='%s'", self.session.call_id, stt_result.text)

        active_system_prompt = self.session.system_prompt
        if active_system_prompt and active_system_prompt.startswith("SCRIPT_MODE:"):
            script_text = active_system_prompt[12:].strip()
            active_system_prompt = (
                f"You are an automated phone representative making an OUTBOUND call.\n"
                f"You called the recipient and recited this script:\n\"{script_text[:1000]}\"\n\n"
                f"The recipient just responded: \"{stt_result.text}\".\n\n"
                f"STRICT INSTRUCTIONS:\n"
                f"1. NEVER say 'Thank you for calling' or 'How can I help you today' (this is an outbound call; you called them).\n"
                f"2. Answer their question or remark politely, accurately, and concisely in ONE single sentence (under 14 words) in their language based on the script.\n"
                f"3. If they say hello, acknowledge and state the main purpose of the call based on the script.\n"
                f"4. If they agree or say OK, thank them for their time and conclude politely."
            )

        payload = {
            "job": {
                "call_id": self.session.call_id,
                "tenant_id": self.session.tenant_id,
                "transcript": stt_result.text,
                "conversation_history": history_before_turn,
                "system_prompt": active_system_prompt,
            },
            "escalation": escalation.value if hasattr(escalation, "value") else str(escalation),
        }

        full_reply_text = ""
        spoken_parts = []  # sentences actually queued for playback (used if the caller interrupts)
        playback_queue = asyncio.Queue()
        llm_first_token_ms = 0.0
        tts_first_audio_ms = 0.0
        t_llm_start = time.perf_counter()
        first_sentence = True

        async def _tts_producer():
            nonlocal full_reply_text, llm_first_token_ms, tts_first_audio_ms, first_sentence
            try:
                async with http_client.stream("POST", "http://127.0.0.1:9093/llm/stream", json=payload, timeout=15.0) as response:
                    if response.status_code == 200:
                        async for line in response.aiter_lines():
                            if cancel_event and cancel_event.is_set():
                                logger.info("call_id=%s Cancelling LLM streaming loop due to barge-in", self.session.call_id)
                                break
                            line = line.strip()
                            if not line:
                                continue
                            data = json.loads(line)
                            if data.get("type") == "sentence":
                                sentence_text = data.get("text", "").strip()
                                if first_sentence:
                                    llm_first_token_ms = (time.perf_counter() - t_llm_start) * 1000.0
                                    logger.info("LLM_FIRST_TOKEN call_id=%s latency_ms=%.1f text='%s'", self.session.call_id, llm_first_token_ms, sentence_text)
                                if sentence_text and not (cancel_event and cancel_event.is_set()):
                                    if first_sentence:
                                        self._set_state(CallState.PROCESSING_TTS)
                                    logger.info("TTS_START call_id=%s sentence='%s'", self.session.call_id, sentence_text)
                                    t_tts_start = time.perf_counter()
                                    tts_result = await self._run_tts(sentence_text)
                                    tts_latency_ms = (time.perf_counter() - t_tts_start) * 1000.0
                                    if first_sentence:
                                        tts_first_audio_ms = tts_latency_ms
                                        first_sentence = False
                                        logger.info("TTS_FIRST_AUDIO call_id=%s latency_ms=%.1f bytes=%d", self.session.call_id, tts_first_audio_ms, len(tts_result.audio_pcm16_8k) if tts_result and tts_result.audio_pcm16_8k else 0)
                                    logger.info("TTS_END call_id=%s total_ms=%.1f bytes=%d", self.session.call_id, tts_latency_ms, len(tts_result.audio_pcm16_8k) if tts_result and tts_result.audio_pcm16_8k else 0)
                                    if tts_result and tts_result.audio_pcm16_8k and not (cancel_event and cancel_event.is_set()):
                                        self._set_state(CallState.AI_SPEAKING)
                                        pcm = tts_result.audio_pcm16_8k
                                        for i in range(0, len(pcm), 320):
                                            playback_queue.put_nowait(pcm[i:i+320])
                                        spoken_parts.append(sentence_text)
                            elif data.get("type") == "done":
                                full_reply_text = data.get("full_text", "")
                                llm_total_ms = (time.perf_counter() - t_llm_start) * 1000.0
                                logger.info("LLM_END call_id=%s full_text='%s' total_ms=%.1f", self.session.call_id, full_reply_text, llm_total_ms)
                                if full_reply_text and not any(msg.get("content") == full_reply_text for msg in self.conversation_history):
                                    self._record_turn("assistant", full_reply_text)
                    else:
                        is_hi = (getattr(self.session, "primary_language", None) in ('hi', 'marwadi'))
                        err_text = "माफ़ कीजिएगा, मुझे आपकी बात समझने में थोड़ी परेशानी हुई।" if is_hi else "I encountered an issue processing your request."
                        tts_result = await self._run_tts(err_text)
                        if tts_result and tts_result.audio_pcm16_8k and not (cancel_event and cancel_event.is_set()):
                            self._set_state(CallState.AI_SPEAKING)
                            pcm = tts_result.audio_pcm16_8k
                            for i in range(0, len(pcm), 320):
                                playback_queue.put_nowait(pcm[i:i+320])
                            if not any(msg.get("content") == err_text for msg in self.conversation_history):
                                self._record_turn("assistant", err_text)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error("Error during LLM/TTS generation: %s", e)
            finally:
                playback_queue.put_nowait(None)

        try:
            producer_task = asyncio.create_task(_tts_producer())
            consumer_task = asyncio.create_task(audio_stream_callback(playback_queue))
            await asyncio.gather(producer_task, consumer_task)
            self._set_state(CallState.LISTENING)
        except asyncio.CancelledError:
            logger.info("call_id=%s handle_utterance_stream received CancelledError", self.session.call_id)
            self.drain_queues()
            while not playback_queue.empty():
                try:
                    playback_queue.get_nowait()
                except Exception:
                    break
            self._set_state(CallState.LISTENING)
            # Interrupted (barge-in): ensure turn is recorded if not already
            interrupted_text = " ".join(spoken_parts)
            if interrupted_text and not any(msg.get("content") in (interrupted_text, full_reply_text) for msg in self.conversation_history):
                self._record_turn("assistant", interrupted_text)
            raise

        final_text = full_reply_text or " ".join(spoken_parts)
        if final_text and not any(msg.get("content") == final_text for msg in self.conversation_history):
            self._record_turn("assistant", final_text)

    async def handle_utterance(self, audio_pcm16_8k: bytes) -> Optional[bytes]:
        """One full turn: audio in -> STT -> LLM -> TTS -> audio out.
        Returns None if the turn should end in human handoff instead
        of AI audio."""

        self._set_state(CallState.PROCESSING_STT)
        stt_result = await self._run_stt(audio_pcm16_8k)

        if stt_result is None or not stt_result.text or not stt_result.text.strip():
            logger.warning("call_id=%s STT returned no transcript or timed out, reprompting user", self.session.call_id)
            self._set_state(CallState.PROCESSING_TTS)
            tts_result = await self._run_tts("I'm sorry, I didn't quite catch that. Could you please say that again?")
            if tts_result and tts_result.audio_pcm16_8k:
                self._set_state(CallState.AI_SPEAKING)
                return tts_result.audio_pcm16_8k
            return None

        from shared.escalation import classify
        escalation = classify(stt_result.text, stt_result.confidence)

        if escalation == EscalationLevel.LOW:
            from shared.ami import AMIRegistry
            if AMIRegistry.client and AMIRegistry.client.is_connected:
                try:
                    await self._request_handoff("user requested human agent")
                    return None
                except Exception as ex:
                    logger.warning("call_id=%s Handoff failed (%s), continuing with LLM", self.session.call_id, ex)
            else:
                logger.info("call_id=%s Human handoff requested but AMI not connected. Continuing with LLM.", self.session.call_id)

        self._set_state(CallState.PROCESSING_LLM)
        llm_result = await self._run_llm(stt_result.text, escalation)

        self.conversation_history.append({"role": "user", "content": stt_result.text})
        self.conversation_history.append({"role": "assistant", "content": llm_result.reply_text})

        self._set_state(CallState.PROCESSING_TTS)
        tts_result = await self._run_tts(llm_result.reply_text)

        self._set_state(CallState.AI_SPEAKING)
        return tts_result.audio_pcm16_8k

    async def _run_stt(self, audio: bytes) -> Optional[STTResult]:
        job = STTJob(
            call_id=self.session.call_id,
            tenant_id=self.session.tenant_id,
            audio_pcm16_8k=audio,
            primary_language=self.session.primary_language,
        )
        try:
            await self.stt_queue.put(job)
        except QueueFullError:
            await self._request_handoff("STT pool at capacity")
            raise CallFailedError("stt_queue_full")

        try:
            result: STTResult = await asyncio.wait_for(self.stt_results.get(), timeout=STT_TIMEOUT_S)
            return result
        except (TimeoutError, asyncio.TimeoutError):
            logger.warning(
                "call_id=%s STT_TIMEOUT after %ss - reprompting instead of crashing",
                self.session.call_id,
                STT_TIMEOUT_S,
            )
            return None

    async def _run_llm(self, transcript: str, escalation: EscalationLevel) -> Optional[LLMResult]:
        job = LLMJob(
            call_id=self.session.call_id,
            tenant_id=self.session.tenant_id,
            transcript=transcript,
            conversation_history=self.conversation_history,
            system_prompt=self.session.system_prompt,
            escalation=escalation,
        )
        try:
            await self.llm_queue.put(job)
        except QueueFullError:
            await self._request_handoff("LLM pool at capacity")
            raise CallFailedError("llm_queue_full")

        try:
            result: LLMResult = await asyncio.wait_for(self.llm_results.get(), timeout=LLM_TIMEOUT_S)
            return result
        except (TimeoutError, asyncio.TimeoutError):
            logger.warning(
                "call_id=%s LLM_TIMEOUT after %ss",
                self.session.call_id,
                LLM_TIMEOUT_S,
            )
            return None

    async def _run_tts(self, text: str) -> Optional[TTSResult]:
        job = TTSJob(
            call_id=self.session.call_id,
            tenant_id=self.session.tenant_id,
            text=text,
            voice_id=self.session.voice_model or "cartesia_hi_sonic",
        )
        try:
            await self.tts_queue.put(job)
        except QueueFullError:
            await self._request_handoff("TTS pool at capacity")
            raise CallFailedError("tts_queue_full")

        try:
            result: TTSResult = await asyncio.wait_for(self.tts_results.get(), timeout=TTS_TIMEOUT_S)
            return result
        except (TimeoutError, asyncio.TimeoutError):
            logger.warning(
                "call_id=%s TTS_TIMEOUT after %ss",
                self.session.call_id,
                TTS_TIMEOUT_S,
            )
            return None

    async def request_handoff_via_dtmf(self) -> None:
        """Helper to trigger handoff immediately when DTMF 0 is received."""
        await self._request_handoff("User pressed 0 on keypad")

    async def _request_handoff(self, reason: str) -> None:
        self.handoff_requested = True
        self.handoff_reason = reason
        if self.session.state not in TRANSFERABLE_STATES and self.session.state != CallState.CREATED:
            logger.warning(
                "call_id=%s handoff requested from non-transferable state %s",
                self.session.call_id, self.session.state,
            )
        logger.info("call_id=%s HUMAN_HANDOFF_REQUESTED reason=%s", self.session.call_id, reason)
        
        # Perform handoff via AMI
        from shared.ami import AMIRegistry
        try:
            channel_name = await AMIRegistry.get_channel_by_uuid(self.session.call_id)
            if not AMIRegistry.client or not AMIRegistry.client.is_connected:
                raise CallFailedError("AMI client not connected")

            # 1. Set SUPERFONE_STATUS=TRANSFER
            logger.info("Setting SUPERFONE_STATUS=TRANSFER on channel %s...", channel_name)
            res = await AMIRegistry.client.send_action("Setvar", {
                "Channel": channel_name,
                "Variable": "SUPERFONE_STATUS",
                "Value": "TRANSFER"
            })
            if res.get("Response", "").lower() != "success":
                raise CallFailedError(f"Setvar TRANSFER failed: {res.get('Message')}")

            # 2. Redirect to 800
            logger.info("Redirecting channel %s to 800@superfone-handoff...", channel_name)
            res = await AMIRegistry.client.send_action("Redirect", {
                "Channel": channel_name,
                "Exten": "800",
                "Context": "superfone-handoff",
                "Priority": "1"
            })
            if res.get("Response", "").lower() != "success":
                raise CallFailedError(f"Redirect failed: {res.get('Message')}")

            logger.info("call_id=%s human transfer accepted and executed successfully.", self.session.call_id)
            self._set_state(CallState.TRANSFERRING)
        except Exception as e:
            logger.error("call_id=%s HANDOFF_FAILED: %s", self.session.call_id, e)
            raise CallFailedError(f"handoff_failed: {e}")


