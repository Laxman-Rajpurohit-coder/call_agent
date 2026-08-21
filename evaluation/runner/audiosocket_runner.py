import asyncio
import json
import os
import re
import struct
import time
import uuid
import wave
from pathlib import Path
from typing import Any, Dict, List, Optional
import numpy as np

from evaluation.runner.trace_collector import TraceCollector


class AudioSocketRunner:
    """
    Deterministic Direct AudioSocket Replay Runner.
    Streams 8kHz PCM16 audio frames directly into the Gateway (port 9092),
    captures agent audio responses, collects structured trace events, and records artifacts.
    """
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 9092,
        frame_size_bytes: int = 320,  # 20ms @ 8kHz PCM16
        frame_interval_s: float = 0.020,
    ):
        self.host = host
        self.port = port
        self.frame_size_bytes = frame_size_bytes
        self.frame_interval_s = frame_interval_s

    async def execute_scenario(
        self,
        scenario: Dict[str, Any],
        run_id: str,
        artifacts_dir: str = "evaluation/artifacts",
    ) -> Dict[str, Any]:
        scenario_id = scenario.get("id", "unknown_scenario")
        target_dir = Path(artifacts_dir) / run_id / scenario_id
        target_dir.mkdir(parents=True, exist_ok=True)

        trace_collector = TraceCollector(
            str(target_dir / "events.jsonl"),
            trace_id=f"eval-{run_id}-{scenario_id}"
        )

        call_uuid = uuid.uuid4()
        trace_collector.emit("call_started", scenario_id=scenario_id, call_uuid=str(call_uuid))

        # Read caller audio WAV
        turn_config = scenario.get("turns", [{}])[0]
        caller_wav_path = turn_config.get("audio_file", "")
        
        caller_pcm_frames: List[bytes] = []
        if os.path.exists(caller_wav_path):
            with wave.open(caller_wav_path, "rb") as wf:
                raw_bytes = wf.readframes(wf.getnframes())
                for i in range(0, len(raw_bytes), self.frame_size_bytes):
                    caller_pcm_frames.append(raw_bytes[i:i + self.frame_size_bytes])

        # Copy caller WAV into target artifact dir as audio_caller.wav and caller.wav
        if os.path.exists(caller_wav_path):
            with open(caller_wav_path, "rb") as sf:
                caller_bytes = sf.read()
            with open(target_dir / "audio_caller.wav", "wb") as df:
                df.write(caller_bytes)
            with open(target_dir / "caller.wav", "wb") as df:
                df.write(caller_bytes)

        agent_pcm_chunks: List[bytes] = []
        transcript_entries: List[Dict[str, Any]] = []
        tools_called: List[Dict[str, Any]] = []
        final_state: Dict[str, Any] = {"status": "in_progress"}

        t_start = time.perf_counter()
        t_speech_end = t_start

        try:
            reader, writer = await asyncio.open_connection(self.host, self.port)
            trace_collector.emit("audiosocket_connected", host=self.host, port=self.port)

            # 1. Send Handshake Header (Type 0x01 = UUID)
            uuid_bytes = call_uuid.bytes
            writer.write(struct.pack("!BH", 0x01, len(uuid_bytes)) + uuid_bytes)
            await writer.drain()

            stop_receiver = asyncio.Event()

            # Background task to receive agent playback audio from Gateway
            async def _receive_agent_audio():
                nonlocal agent_pcm_chunks
                first_agent_frame = True
                while not stop_receiver.is_set():
                    try:
                        hdr = await asyncio.wait_for(reader.readexactly(3), timeout=0.1)
                        p_type, p_len = struct.unpack("!BH", hdr)
                        payload = await reader.readexactly(p_len)
                        if p_type == 0x10 and payload:
                            if first_agent_frame:
                                t_now = time.perf_counter()
                                speech_end_to_playback_ms = round((t_now - t_speech_end) * 1000) if t_speech_end else 0
                                call_start_to_playback_ms = round((t_now - t_start) * 1000)
                                trace_collector.emit(
                                    "agent_playback_started",
                                    caller_speech_end_to_playback_start_ms=speech_end_to_playback_ms,
                                    call_start_to_playback_start_ms=call_start_to_playback_ms,
                                )
                                first_agent_frame = False
                            agent_pcm_chunks.append(payload)
                        elif p_type == 0x00:
                            trace_collector.emit("agent_hangup_received")
                            break
                    except asyncio.TimeoutError:
                        continue
                    except Exception as ex:
                        trace_collector.emit("receiver_exception", error=str(ex))
                        break

            recv_task = asyncio.create_task(_receive_agent_audio())

            # 2. Check if this is a Barge-In scenario
            barge_cfg = scenario.get("barge_in")
            if barge_cfg:
                # ── Barge-In Sequence ──
                # Phase 1: Stream initial caller query
                init_path = barge_cfg.get("initial_audio", "")
                init_frames = []
                if os.path.exists(init_path):
                    with wave.open(init_path, "rb") as wf:
                        raw_b = wf.readframes(wf.getnframes())
                        for i in range(0, len(raw_b), self.frame_size_bytes):
                            init_frames.append(raw_b[i:i + self.frame_size_bytes])

                trace_collector.emit("barge_in_initial_speech_started", frame_count=len(init_frames))
                for frame in init_frames:
                    if len(frame) < self.frame_size_bytes:
                        frame = frame + b"\x00" * (self.frame_size_bytes - len(frame))
                    writer.write(struct.pack("!BH", 0x10, len(frame)) + frame)
                    await writer.drain()
                    await asyncio.sleep(self.frame_interval_s)

                # Trailing silence to trigger initial VAD
                silence_frame = b"\x00" * self.frame_size_bytes
                for _ in range(35):  # 700ms silence
                    writer.write(struct.pack("!BH", 0x10, len(silence_frame)) + silence_frame)
                    await writer.drain()
                    await asyncio.sleep(self.frame_interval_s)

                # Phase 2: Wait for agent playback to begin
                wait_agent_deadline = time.perf_counter() + 6.0
                while time.perf_counter() < wait_agent_deadline and len(agent_pcm_chunks) < 20:
                    await asyncio.sleep(0.05)

                # Wait specified delay into agent speech (e.g. 1000ms)
                inter_delay_ms = barge_cfg.get("interrupt_after_playback_ms", 1000)
                await asyncio.sleep(inter_delay_ms / 1000.0)

                # Phase 3: Inject barge-in interruption audio
                int_path = barge_cfg.get("interrupt_audio", "")
                int_frames = []
                if os.path.exists(int_path):
                    with wave.open(int_path, "rb") as wf:
                        raw_b = wf.readframes(wf.getnframes())
                        for i in range(0, len(raw_b), self.frame_size_bytes):
                            int_frames.append(raw_b[i:i + self.frame_size_bytes])

                trace_collector.emit("barge_in_interruption_injected", frame_count=len(int_frames))
                t_speech_end = time.perf_counter()
                for frame in int_frames:
                    if len(frame) < self.frame_size_bytes:
                        frame = frame + b"\x00" * (self.frame_size_bytes - len(frame))
                    writer.write(struct.pack("!BH", 0x10, len(frame)) + frame)
                    await writer.drain()
                    await asyncio.sleep(self.frame_interval_s)

                # Trailing silence after interruption
                for _ in range(50):
                    writer.write(struct.pack("!BH", 0x10, len(silence_frame)) + silence_frame)
                    await writer.drain()
                    await asyncio.sleep(self.frame_interval_s)

            else:
                # ── Normal / Quiet / Noise Single Turn ──
                trace_collector.emit("caller_speech_started", frame_count=len(caller_pcm_frames))
                for frame in caller_pcm_frames:
                    if len(frame) < self.frame_size_bytes:
                        frame = frame + b"\x00" * (self.frame_size_bytes - len(frame))
                    writer.write(struct.pack("!BH", 0x10, len(frame)) + frame)
                    await writer.drain()
                    await asyncio.sleep(self.frame_interval_s)

                t_speech_end = time.perf_counter()
                trace_collector.emit("caller_speech_ended", duration_s=round(len(caller_pcm_frames) * 0.02, 2))

                # 3. Stream 1.0s of trailing silence to trigger VAD endpointing
                silence_frame = b"\x00" * self.frame_size_bytes
                for _ in range(50):  # 50 frames = 1.0s
                    writer.write(struct.pack("!BH", 0x10, len(silence_frame)) + silence_frame)
                    await writer.drain()
                    await asyncio.sleep(self.frame_interval_s)

            # 4. Wait for agent to respond and finish speaking (up to 8.0s timeout)
            wait_deadline = time.perf_counter() + 8.0
            last_chunk_count = 0
            quiet_period = 0

            while time.perf_counter() < wait_deadline:
                await asyncio.sleep(0.5)
                current_count = len(agent_pcm_chunks)
                if current_count > 0 and current_count == last_chunk_count:
                    quiet_period += 1
                    if quiet_period >= 4:  # 2.0s of silence after speech -> playback done
                        break
                else:
                    quiet_period = 0
                last_chunk_count = current_count

            stop_receiver.set()
            recv_task.cancel()

            # Close connection gracefully
            try:
                writer.write(struct.pack("!BH", 0x00, 0))
                await writer.drain()
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

            trace_collector.emit(
                "agent_playback_completed",
                frames_received=len(agent_pcm_chunks),
                total_duration_s=round(len(agent_pcm_chunks) * 0.02, 2)
            )
            final_state = {"status": "completed", "error": None}

        except Exception as e:
            trace_collector.emit("service_error", error=str(e))
            final_state = {"status": "failed", "error": str(e)}

        trace_collector.emit("call_ended", duration_ms=round((time.perf_counter() - t_start) * 1000))

        # Save received agent audio as both audio_agent.wav and agent.wav
        agent_raw = b"".join(agent_pcm_chunks)
        for wav_name in ("audio_agent.wav", "agent.wav"):
            with wave.open(str(target_dir / wav_name), "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(8000)
                wf.writeframes(agent_raw)

        # Inspect gateway logs specifically for this scenario's call_uuid
        with open("call_gateway.log", "r", encoding="utf-8", errors="ignore") as f:
            log_lines = f.readlines()

        captured_transcript = ""
        agent_response_text = ""
        stt_conf = 0.0
        for line in log_lines:
            if str(call_uuid) in line:
                if "STT_END" in line and "transcript=" in line:
                    try:
                        m = re.search(r"transcript='(.*)' latency_ms=", line)
                        if m:
                            captured_transcript = m.group(1)
                        if "confidence_proxy=" in line:
                            stt_conf = float(line.split("confidence_proxy=")[1].split()[0])
                    except Exception:
                        pass
                elif "LLM_END" in line and "full_text=" in line:
                    try:
                        m = re.search(r"full_text='(.*)' total_ms=", line)
                        if m:
                            agent_response_text = m.group(1)
                    except Exception:
                        pass

        # Emit stt_result event in trace collector
        if captured_transcript:
            trace_collector.emit("stt_result", text=captured_transcript, confidence=stt_conf)
        elif agent_pcm_chunks:
            trace_collector.emit("stt_rejected", reason="empty_or_low_energy")

        # Write transcript.jsonl
        with open(target_dir / "transcript.jsonl", "w", encoding="utf-8") as tf:
            if captured_transcript:
                tf.write(json.dumps({"speaker": "caller", "text": captured_transcript}) + "\n")
            if agent_response_text:
                tf.write(json.dumps({"speaker": "agent", "text": agent_response_text}) + "\n")

        # Write tools.json
        with open(target_dir / "tools.json", "w", encoding="utf-8") as to_f:
            json.dump(tools_called, to_f, indent=2)

        # Write final_state.json
        with open(target_dir / "final_state.json", "w", encoding="utf-8") as fs_f:
            json.dump(final_state, fs_f, indent=2)

        return {
            "scenario_id": scenario_id,
            "run_id": run_id,
            "target_dir": str(target_dir),
            "caller_transcript": captured_transcript,
            "agent_response": agent_response_text,
            "agent_audio_bytes": len(agent_raw),
            "agent_audio_duration_s": round(len(agent_raw) / 16000.0, 2),
            "final_state": final_state,
        }
