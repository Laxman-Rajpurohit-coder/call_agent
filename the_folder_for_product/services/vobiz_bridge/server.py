"""
Vobiz WebSocket bridge server.

This is the HTTP/WebSocket entry point Vobiz talks to directly (Route A: no Asterisk, no SIP trunk).
It has two jobs:

  1. /answer  - Vobiz POSTs (or GETs) here the instant a call is answered. We mint our own call id,
     remember the caller/dialed number against it, and return VobizXML telling Vobiz to open a
     bidirectional WebSocket stream to our /ws, with our call id embedded in the URL.
  2. /ws      - Vobiz opens this WebSocket and streams the call as JSON (start/media/dtmf/stop events).
     We hand every message to a VobizCallBridge, which re-encodes the audio and speaks the AudioSocket
     protocol to the existing call_gateway (port 9092) - so the whole proven VAD/STT/LLM/TTS/handoff/CRM
     pipeline behind the gateway runs completely unchanged.

This supersedes the old services/vobiz_webhook/server.py (which dials out to an Asterisk SIP trunk -
Route B). Point the Vobiz Application's Answer URL at ONE of the two routes, not both.

Run standalone:   python -m services.vobiz_bridge.server
Or import `app` and run it under start_services.py's launcher like the other microservices.
"""
import logging
import os
import uuid
from typing import Dict, Optional

import uvicorn
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import PlainTextResponse, Response

from services.dashboard.app.config import settings
from services.dashboard.app.services.call_lifecycle import astart_call
from services.vobiz_bridge.bridge import PendingCalls, VobizCallBridge, build_answer_xml, public_base_url, ws_url

# Shared with services/call_gateway/server.py, so the live monitor's tailer and anyone debugging a
# call sees the HTTP layer (VOBIZ_ANSWER, VOBIZ_BRIDGE ...) interleaved chronologically with the
# AI turns (USER_UTTERANCE / AI_RESPONSE) in one file, in the order the call actually happened.
# NOTE: two processes append to this same file. Python's FileHandler opens in 'a' mode, which is
# safe for whole-line writes on both Windows and POSIX at this log volume; if lines ever start
# interleaving mid-line under heavy concurrent load, split this back into its own file.
_LOG_PATH = settings.CALL_GATEWAY_LOG
os.makedirs(os.path.dirname(os.path.abspath(_LOG_PATH)), exist_ok=True)
_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(name)s - %(message)s")
_file_handler = logging.FileHandler(_LOG_PATH, encoding="utf-8")
_file_handler.setFormatter(_formatter)
_console_handler = logging.StreamHandler()
_console_handler.setFormatter(_formatter)
logging.basicConfig(level=logging.INFO, handlers=[_file_handler, _console_handler])
logger = logging.getLogger("vobiz_bridge.server")
logger.info("Vobiz bridge logging to %s", _LOG_PATH)

PORT = int(os.environ.get("VOBIZ_BRIDGE_PORT", "9098"))
PUBLIC_URL = os.environ.get("VOBIZ_PUBLIC_URL", "").strip()   # e.g. https://drool-envoy-sandy.ngrok-free.dev
GATEWAY_HOST = os.environ.get("CALL_GATEWAY_HOST", "127.0.0.1")
GATEWAY_PORT = int(os.environ.get("CALL_GATEWAY_PORT", "9092"))

pending_calls = PendingCalls()
app = FastAPI(title="Vobiz WebSocket Bridge")

# Aliases tried in order. We do NOT know Vobiz's exact field names for certain (the docs confirm
# From/To/Direction exist; the call-id field name is a guess) - the raw form is logged on every
# call below specifically so the first real call can correct this list if needed.
FROM_FIELDS = ("From", "CallerId", "Caller", "caller_id", "from")
TO_FIELDS = ("To", "Called", "DialedNumber", "to")
DIRECTION_FIELDS = ("Direction", "CallDirection", "direction")
VOBIZ_ID_FIELDS = ("CallSid", "CallUUID", "call_uuid", "RequestUUID", "uuid", "StreamSid")


def _first(values: dict, names, default: str = "") -> str:
    for name in names:
        v = values.get(name)
        if v not in (None, ""):
            return str(v)
    return default


@app.api_route("/answer", methods=["GET", "POST"])
async def answer(request: Request) -> Response:
    """The URL Vobiz fetches the moment a call is answered."""
    try:
        form = dict(await request.form())
    except Exception:
        form = {}
    values = {**dict(request.query_params), **form}   # form wins over query string if both present

    from_number = _first(values, FROM_FIELDS, "unknown")
    to_number = _first(values, TO_FIELDS, "unknown")
    direction = _first(values, DIRECTION_FIELDS, "inbound").lower()
    if "outbound" in direction:
        direction = "outbound"
    else:
        direction = "inbound"
    vobiz_call_id = _first(values, VOBIZ_ID_FIELDS)

    # If cid query parameter was passed from caller/main.py, use that exact call id!
    cid_param = request.query_params.get("cid") or values.get("cid")
    our_call_id = cid_param.strip() if cid_param else str(uuid.uuid4())
    pending_calls.add(our_call_id, from_number, to_number, direction, vobiz_call_id)

    logger.info("VOBIZ_ANSWER our_id=%s vobiz_id=%s from=%s to=%s direction=%s raw_fields=%s",
               our_call_id, vobiz_call_id or "-", from_number, to_number, direction, values)

    base_url = public_base_url(dict(request.headers), PUBLIC_URL)
    stream_url = ws_url(base_url, our_call_id)
    xml = build_answer_xml(stream_url, status_callback_url=f"{base_url}/stream-status")
    return Response(content=xml, media_type="application/xml")


ACTIVE_BRIDGES: Dict[str, VobizCallBridge] = {}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    cid_hint: Optional[str] = websocket.query_params.get("cid")

    async def send_json(payload: dict) -> None:
        await websocket.send_json(payload)

    async def close_ws() -> None:
        try:
            await websocket.close()
        except Exception:
            pass

    bridge = VobizCallBridge(
        send_json, close_ws, pending_calls, cid_hint=cid_hint,
        gateway_host=GATEWAY_HOST, gateway_port=GATEWAY_PORT,
        crm_start=astart_call, recordings_dir=settings.RECORDINGS_DIR,
    )
    if cid_hint:
        ACTIVE_BRIDGES[cid_hint] = bridge
    try:
        while True:
            message = await websocket.receive_text()
            await bridge.handle_message(message)
            if bridge.call_id and bridge.call_id not in ACTIVE_BRIDGES:
                ACTIVE_BRIDGES[bridge.call_id] = bridge
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("VOBIZ_BRIDGE websocket error (cid=%s)", cid_hint)
    finally:
        if cid_hint:
            ACTIVE_BRIDGES.pop(cid_hint, None)
        if bridge.call_id:
            ACTIVE_BRIDGES.pop(bridge.call_id, None)
        await bridge.close(from_gateway=False)


@app.post("/calls/{call_id}/hangup")
async def hangup_call_bridge(call_id: str) -> Response:
    """Terminates an active Vobiz call bridge session and carrier call."""
    bridge = ACTIVE_BRIDGES.get(call_id)
    if bridge:
        logger.info("VOBIZ_BRIDGE terminating active call_id=%s via hangup API", call_id)
        await bridge.close(from_gateway=False)
        return Response(status_code=200, content='{"status":"hung_up","call_id":"' + call_id + '"}', media_type="application/json")
    return Response(status_code=404, content='{"error":"Call bridge not found for ID ' + call_id + '"}', media_type="application/json")


@app.post("/hangup")
async def hangup(request: Request) -> Response:
    try:
        form = dict(await request.form())
    except Exception:
        form = {}
    params = dict(request.query_params)
    target = params.get("call_id") or form.get("call_id") or params.get("cid") or form.get("cid")
    if target and target in ACTIVE_BRIDGES:
        logger.info("VOBIZ_BRIDGE terminating target=%s via form hangup", target)
        await ACTIVE_BRIDGES[target].close(from_gateway=False)
    return Response(status_code=204)


@app.post("/stream-status")
async def stream_status(request: Request) -> Response:
    try:
        data = dict(await request.form())
        logger.info("VOBIZ_STREAM_STATUS %s", data)
    except Exception:
        pass
    return Response(status_code=204)


@app.get("/health")
async def health() -> PlainTextResponse:
    return PlainTextResponse(f"Vobiz WebSocket Bridge OK (gateway={GATEWAY_HOST}:{GATEWAY_PORT}, pending={len(pending_calls)})")


if __name__ == "__main__":
    logger.info("Vobiz WebSocket Bridge listening on 0.0.0.0:%d (call gateway at %s:%d)",
               PORT, GATEWAY_HOST, GATEWAY_PORT)
    logger.info("Answer URL to configure in Vobiz: <your public url>/answer")
    uvicorn.run(app, host="0.0.0.0", port=PORT)
