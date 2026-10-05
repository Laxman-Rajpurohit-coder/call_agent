"""
Vobiz <-> AudioSocket bridge.

Vobiz streams a call to us over a WebSocket (JSON messages carrying base64 mu-law audio).  The call
gateway (services/call_gateway) speaks the AudioSocket protocol (binary packets carrying 8 kHz PCM16).
This module translates between the two, so the whole proven pipeline behind the gateway - VAD, STT,
LLM, TTS, barge-in, transcript capture, CRM recording, heartbeats - is reused unchanged and no Asterisk
(and no UDP/RTP port forwarding) is needed.  It also writes the call recording (caller left, AI right).

    Vobiz  --start/media/dtmf/stop-->  bridge  --AudioSocket UUID/audio/DTMF/hangup-->  call gateway
    Vobiz  <--------playAudio--------  bridge  <---------AudioSocket audio/hangup------  call gateway

AudioSocket packet: 1 byte type + 2 bytes big-endian length + payload.
    0x01 = call UUID (16 bytes)   0x10 = audio (320 bytes = 20 ms)   0x03 = DTMF digit   0x00 = hangup

The transport-independent core (``VobizCallBridge``) never imports a web framework, so it can be tested
with plain asyncio.
"""
import asyncio
import base64
import json
import logging
import os
import struct
import time
import uuid
import wave
from collections import deque
from typing import Any, Awaitable, Callable, Deque, Dict, Mapping, Optional
from urllib.parse import quote
from xml.sax.saxutils import escape, quoteattr

from services.vobiz_bridge import audio

logger = logging.getLogger("vobiz_bridge")

T_HANGUP, T_UUID, T_DTMF, T_AUDIO = 0x00, 0x01, 0x03, 0x10
SILENCE_FRAME = b"\x00" * audio.FRAME_BYTES
MAX_QUEUED_AI_FRAMES = 500          # 10 s; bounds memory if the caller's audio ever stops

SendJson = Callable[[Dict[str, Any]], Awaitable[None]]
CloseWs = Callable[[], Awaitable[None]]


# --------------------------------------------------------------------------------------
# Answer-URL helpers (pure)
# --------------------------------------------------------------------------------------

def as_uuid(value: Any) -> Optional[str]:
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, AttributeError, TypeError):
        return None


def public_base_url(headers: Mapping[str, str], env_url: str = "") -> str:
    """The public https://host that Vobiz used to reach us (works behind ngrok without configuration)."""
    if env_url:
        return env_url.strip().rstrip("/")
    host = (headers.get("x-forwarded-host") or headers.get("host") or "localhost").split(",")[0].strip()
    proto = (headers.get("x-forwarded-proto") or "").split(",")[0].strip().lower()
    if proto not in ("http", "https"):
        proto = "http" if host.startswith(("localhost", "127.")) else "https"
    return f"{proto}://{host}"


def ws_url(base_url: str, cid: str) -> str:
    scheme = "wss" if base_url.startswith("https://") else "ws"
    rest = base_url.split("://", 1)[1]
    return f"{scheme}://{rest}/ws?cid={quote(str(cid), safe='')}"


def build_answer_xml(stream_url: str, status_callback_url: Optional[str] = None) -> str:
    """VobizXML for the Answer URL: stream the call to our WebSocket, hang up when the stream ends."""
    attrs = 'bidirectional="true" audioTrack="inbound" keepCallAlive="true" contentType="audio/x-mulaw;rate=8000"'
    if status_callback_url:
        attrs += f" statusCallbackUrl={quoteattr(status_callback_url)} statusCallbackMethod=\"POST\""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<Response>\n"
        f"    <Stream {attrs}>\n"
        f"        {escape(stream_url)}\n"
        "    </Stream>\n"
        "    <Hangup/>\n"
        "</Response>"
    )


class PendingCalls:
    """Call details from /answer (caller, dialed number) waiting for the matching WebSocket."""

    def __init__(self, ttl_s: float = 30.0):
        self._ttl = ttl_s
        self._items: Dict[str, Dict[str, Any]] = {}

    def _prune(self) -> None:
        cutoff = time.monotonic() - self._ttl
        for key in [k for k, v in self._items.items() if v["ts"] < cutoff]:
            del self._items[key]

    def add(self, key: str, from_number: str, to_number: str, direction: str = "inbound", call_uuid: str = "") -> None:
        self._prune()
        self._items[key] = {"from": from_number, "to": to_number, "direction": direction,
                            "call_uuid": call_uuid, "ts": time.monotonic()}

    def claim(self, key: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Exact match if we know the key, else the most recent unclaimed call (flagged as a fallback)."""
        self._prune()
        if key and key in self._items:
            return dict(self._items.pop(key), fallback=False)
        if self._items:
            newest = max(self._items, key=lambda k: self._items[k]["ts"])
            return dict(self._items.pop(newest), fallback=True)
        return None

    def __len__(self) -> int:
        self._prune()
        return len(self._items)


# --------------------------------------------------------------------------------------
# Recording
# --------------------------------------------------------------------------------------

class StereoRecorder:
    """Caller on the left channel, AI on the right, 8 kHz 16-bit."""

    def __init__(self, path: str):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self.path = path
        self._wav = wave.open(path, "wb")
        self._wav.setnchannels(2)
        self._wav.setsampwidth(2)
        self._wav.setframerate(8000)

    def write(self, caller_frame: bytes, ai_frame: bytes) -> None:
        self._wav.writeframes(audio.interleave_stereo(caller_frame, ai_frame))

    def close(self) -> None:
        try:
            self._wav.close()
        except Exception:
            pass


# --------------------------------------------------------------------------------------
# The bridge for ONE call
# --------------------------------------------------------------------------------------

class VobizCallBridge:
    def __init__(
        self,
        send_json: SendJson,
        close_ws: CloseWs,
        pending: PendingCalls,
        cid_hint: Optional[str] = None,
        gateway_host: str = "127.0.0.1",
        gateway_port: int = 9092,
        crm_start: Optional[Callable[..., Awaitable[Any]]] = None,
        recordings_dir: Optional[str] = None,
    ):
        self._send_json, self._close_ws, self._pending = send_json, close_ws, pending
        self._cid_hint = cid_hint
        self._gw_host, self._gw_port = gateway_host, gateway_port
        self._crm_start = crm_start
        self._recordings_dir = recordings_dir

        self.call_id: Optional[str] = None
        self.stream_id: Optional[str] = None
        self.from_number = "unknown"
        self.to_number = "unknown"
        self.frames_from_caller = 0
        self.frames_to_caller = 0

        self._started = False
        self._closed = False
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._gw_task: Optional[asyncio.Task] = None
        self._slicer = audio.FrameSlicer()
        self._ai_frames: Deque[bytes] = deque()
        self._recorder: Optional[StereoRecorder] = None
        self._encoding, self._rate = "audio/x-mulaw", 8000
        self._warned_format = False

    # ---- Vobiz -> gateway -------------------------------------------------------------

    async def handle_message(self, raw: str) -> None:
        try:
            data = json.loads(raw)
        except (ValueError, TypeError):
            logger.warning("VOBIZ_BRIDGE ignoring a non-JSON message")
            return
        event = data.get("event")
        if event == "start":
            await self._on_start(data)
        elif event == "media":
            await self._on_media(data)
        elif event == "dtmf":
            await self._on_dtmf(data)
        elif event == "stop":
            logger.info("VOBIZ_BRIDGE call_id=%s stop event received", self.call_id)
            await self.close()
        # playedStream / clearedAudio / checkpoint acknowledgements need no action

    async def _on_start(self, data: Dict[str, Any]) -> None:
        if self._started:
            return
        self._started = True
        start = data.get("start") or {}
        self.stream_id = data.get("streamId") or start.get("streamId")
        fmt = start.get("mediaFormat") or {}
        self._encoding = str(fmt.get("encoding", "audio/x-mulaw")).lower()
        try:
            self._rate = int(fmt.get("sampleRate", 8000) or 8000)
        except (TypeError, ValueError):
            self._rate = 8000

        hint = (self._cid_hint or start.get("callId") or start.get("callUUID")
                or data.get("callId") or data.get("callUUID"))
        meta = self._pending.claim(hint)
        direction = "inbound"
        vobiz_uuid = ""
        if meta:
            self.from_number, self.to_number = meta["from"], meta["to"]
            direction, vobiz_uuid = meta["direction"], meta["call_uuid"]
            if meta["fallback"]:
                logger.warning("VOBIZ_BRIDGE could not match the WebSocket to a call by id; assumed the most "
                               "recent /answer (only safe with one call at a time)")
        else:
            logger.warning("VOBIZ_BRIDGE no /answer details for this stream - caller/dialed number unknown")

        # Prioritize our pre-created call ID (cid_hint / hint) so outbound script, prompt, and voice configurations are preserved
        self.call_id = as_uuid(self._cid_hint) or as_uuid(hint) or as_uuid(vobiz_uuid) or str(uuid.uuid4())
        logger.info("VOBIZ_BRIDGE call_id=%s vobiz_uuid=%s from=%s to=%s direction=%s format=%s@%s stream=%s",
                    self.call_id, vobiz_uuid or "-", self.from_number, self.to_number, direction,
                    self._encoding, self._rate, self.stream_id)

        # Store vobiz_uuid correlation on the database session
        if vobiz_uuid:
            try:
                from services.dashboard.app.database import SessionLocal
                from services.dashboard.app.models.crm import CallSession
                with SessionLocal() as db_s:
                    s_rec = db_s.query(CallSession).filter(CallSession.id == self.call_id).first()
                    if s_rec:
                        c_fields = dict(s_rec.custom_fields or {})
                        c_fields["vobiz_call_uuid"] = vobiz_uuid
                        s_rec.custom_fields = c_fields
                        db_s.commit()
            except Exception as v_ex:
                logger.warning("VOBIZ_BRIDGE could not record vobiz_uuid correlation: %s", v_ex)

        # Create the CRM session NOW with the real caller/dialed number; the gateway's own start_call
        # then finds it (start_call is idempotent per call id).
        if self._crm_start:
            try:
                await self._crm_start(call_id=self.call_id, from_number=self.from_number,
                                      to_number=self.to_number, direction=direction, provider="vobiz")
            except Exception as ex:
                logger.error("VOBIZ_BRIDGE CRM start failed for %s: %s", self.call_id, ex)

        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self._gw_host, self._gw_port), 5)
        except Exception as ex:
            logger.error("VOBIZ_BRIDGE cannot reach the call gateway at %s:%s (%s) - is it running?",
                         self._gw_host, self._gw_port, ex)
            await self.close(from_gateway=True)
            return
        self._writer.write(struct.pack("!BH", T_UUID, 16) + uuid.UUID(self.call_id).bytes)
        await self._writer.drain()
        self._gw_task = asyncio.create_task(self._gateway_reader())

        if self._recordings_dir:
            try:
                self._recorder = StereoRecorder(os.path.join(self._recordings_dir, f"{self.call_id}.wav"))
            except Exception as ex:
                logger.error("VOBIZ_BRIDGE cannot open the recording file: %s", ex)

    def _to_pcm8k(self, raw: bytes) -> bytes:
        enc = self._encoding
        if "mulaw" in enc or "ulaw" in enc or "pcmu" in enc:
            return audio.ulaw_to_pcm16(raw)                  # 8 kHz mu-law (what we request)
        if "l16" in enc or "linear" in enc or "pcm" in enc:
            return audio.pcm16_16k_to_8k(raw) if self._rate == 16000 else raw
        if not self._warned_format:
            logger.warning("VOBIZ_BRIDGE unexpected audio format %r@%s - treating as 8 kHz mu-law", enc, self._rate)
            self._warned_format = True
        return audio.ulaw_to_pcm16(raw)

    async def _on_media(self, data: Dict[str, Any]) -> None:
        payload = (data.get("media") or {}).get("payload")
        if not payload or self._writer is None or self._closed:
            return
        try:
            pcm = self._to_pcm8k(base64.b64decode(payload))
        except Exception:
            logger.warning("VOBIZ_BRIDGE undecodable audio chunk ignored")
            return
        try:
            for frame in self._slicer.push(pcm):
                self._writer.write(struct.pack("!BH", T_AUDIO, len(frame)) + frame)
                self.frames_from_caller += 1
                self._record(frame)
            await self._writer.drain()
        except (ConnectionError, OSError):
            await self.close(from_gateway=True)

    async def _on_dtmf(self, data: Dict[str, Any]) -> None:
        d = data.get("dtmf")
        digit = (d.get("digit") if isinstance(d, dict) else d) or data.get("digit")
        if not digit or self._writer is None or self._closed:
            return
        try:
            self._writer.write(struct.pack("!BH", T_DTMF, 1) + str(digit)[0].encode("ascii", "ignore"))
            await self._writer.drain()
            logger.info("VOBIZ_BRIDGE call_id=%s DTMF %s", self.call_id, digit)
        except (ConnectionError, OSError):
            await self.close(from_gateway=True)

    def _record(self, caller_frame: bytes) -> None:
        if self._recorder is None:
            return
        ai = self._ai_frames.popleft() if self._ai_frames else SILENCE_FRAME
        try:
            self._recorder.write(caller_frame, ai)
        except Exception:
            self._recorder = None

    # ---- gateway -> Vobiz -------------------------------------------------------------

    async def _gateway_reader(self) -> None:
        try:
            while True:
                t, ln = struct.unpack("!BH", await self._reader.readexactly(3))
                payload = await self._reader.readexactly(ln) if ln else b""
                if t == T_AUDIO and payload:
                    self.frames_to_caller += 1
                    self._ai_frames.append(payload)
                    if len(self._ai_frames) > MAX_QUEUED_AI_FRAMES:
                        self._ai_frames.popleft()
                    await self._send_json({
                        "event": "playAudio",
                        "streamId": self.stream_id,
                        "media": {
                            "contentType": "audio/x-l16",
                            "sampleRate": 8000,
                            "payload": base64.b64encode(payload).decode("ascii"),
                        },
                    })
                elif t == T_HANGUP:
                    logger.info("VOBIZ_BRIDGE call_id=%s the gateway ended the call", self.call_id)
                    break
        except (asyncio.IncompleteReadError, ConnectionError, OSError):
            pass
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("VOBIZ_BRIDGE gateway reader failed for %s", self.call_id)
        await self.close(from_gateway=True)

    # ---- shutdown -----------------------------------------------------------------------

    async def close(self, from_gateway: bool = False) -> None:
        if self._closed:
            return
        self._closed = True
        if self._writer is not None:
            try:
                if not from_gateway:                       # the caller hung up first: tell the gateway
                    self._writer.write(struct.pack("!BH", T_HANGUP, 0))
                    await self._writer.drain()
                self._writer.close()
            except Exception:
                pass
        if self._gw_task is not None and self._gw_task is not asyncio.current_task():
            self._gw_task.cancel()
        if self._recorder is not None:
            self._recorder.close()
        try:
            await self._close_ws()
        except Exception:
            pass
        logger.info("VOBIZ_BRIDGE call_id=%s closed (caller frames=%d, AI frames=%d)",
                    self.call_id, self.frames_from_caller, self.frames_to_caller)
