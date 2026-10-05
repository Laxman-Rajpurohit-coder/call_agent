"""
Tests for services/vobiz_bridge/server.py (the /answer + /ws HTTP layer).

Run from the product folder:   python -m pytest tests/test_vobiz_bridge_server.py -v

Everything here runs in-process via FastAPI's TestClient - no ngrok, no real Vobiz account, and no
real call_gateway needs to be running EXCEPT for test_full_call_over_websocket, which spins up a
tiny fake AudioSocket server on localhost to stand in for it.

NOTE: I (Claude) could not execute this file myself - my sandbox has no network access to install
fastapi/httpx/uvicorn, which are already in this project's requirements.txt. Please run this for
real and report any failures back before trusting the /answer and /ws wiring.
"""
import array
import asyncio
import base64
import json
import os
import struct
import sys
import tempfile
import threading
import time
import uuid
import xml.etree.ElementTree as ET

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture()
def client(monkeypatch, tmp_path):
    """Import the server fresh per test with a patched CRM hook and an isolated recordings dir,
    so tests never touch the real voice_crm.db or the real recordings/ folder."""
    import importlib
    from services.dashboard.app import config as dashboard_config
    monkeypatch.setattr(dashboard_config.settings, "RECORDINGS_DIR", str(tmp_path))

    import services.vobiz_bridge.server as server_module
    importlib.reload(server_module)  # fresh `pending_calls` per test

    calls = []

    async def fake_astart_call(**kw):
        calls.append(kw)
        return {"call_id": kw["call_id"], "organization_id": "org1"}

    monkeypatch.setattr(server_module, "astart_call", fake_astart_call)
    with TestClient(server_module.app) as c:
        c.crm_calls = calls
        c.server_module = server_module
        yield c


# ----------------------------------------------------------------------------------------
# /answer
# ----------------------------------------------------------------------------------------

def test_answer_returns_valid_xml_with_a_websocket_url(client):
    resp = client.post("/answer", data={"From": "+919812345678", "To": "+918065354620", "Direction": "inbound"})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/xml")

    root = ET.fromstring(resp.text)
    assert root.tag == "Response"
    stream = root.find("Stream")
    assert stream is not None and stream.attrib["bidirectional"] == "true"
    ws_url = stream.text.strip()
    assert ws_url.startswith("wss://testserver/ws?cid=")

    # the cid in the URL must be a real, resolvable pending call
    cid = ws_url.split("cid=")[1]
    meta = client.server_module.pending_calls.claim(cid)
    assert meta is not None
    assert meta["from"] == "+919812345678" and meta["to"] == "+918065354620" and meta["direction"] == "inbound"


def test_answer_tries_field_name_aliases(client):
    """We don't know Vobiz's exact field names for certain - confirm the alias fallbacks work."""
    resp = client.post("/answer", data={"Caller": "+919000000001", "Called": "+918065354620"})
    ws_url = ET.fromstring(resp.text).find("Stream").text.strip()
    cid = ws_url.split("cid=")[1]
    meta = client.server_module.pending_calls.claim(cid)
    assert meta["from"] == "+919000000001" and meta["to"] == "+918065354620"


def test_answer_with_no_fields_at_all_does_not_crash(client):
    resp = client.post("/answer", data={})
    assert resp.status_code == 200
    ET.fromstring(resp.text)  # still well-formed XML


def test_answer_accepts_get_too(client):
    resp = client.get("/answer", params={"From": "+919812345678", "To": "+918065354620"})
    assert resp.status_code == 200
    assert "<Stream" in resp.text


def test_answer_records_the_vobiz_call_id_for_correlation_only(client):
    resp = client.post("/answer", data={"From": "+919812345678", "To": "+918065354620", "CallSid": "CA-real-id-123"})
    ws_url = ET.fromstring(resp.text).find("Stream").text.strip()
    our_cid = ws_url.split("cid=")[1]
    assert our_cid != "CA-real-id-123"                    # we mint our own key, we don't reuse Vobiz's
    meta = client.server_module.pending_calls.claim(our_cid)
    assert meta["call_uuid"] == "CA-real-id-123"           # but we do remember it


def test_each_answer_call_gets_a_distinct_id(client):
    urls = []
    for _ in range(3):
        resp = client.post("/answer", data={"From": "+919812345678", "To": "+918065354620"})
        urls.append(ET.fromstring(resp.text).find("Stream").text.strip())
    cids = [u.split("cid=")[1] for u in urls]
    assert len(set(cids)) == 3


def test_hangup_and_stream_status_and_health_endpoints(client):
    assert client.post("/hangup", data={"CallSid": "x"}).status_code == 204
    assert client.post("/stream-status", data={"streamId": "s1", "status": "ended"}).status_code == 204
    r = client.get("/health")
    assert r.status_code == 200 and "OK" in r.text


# ----------------------------------------------------------------------------------------
# /ws  (a full call, with a fake AudioSocket gateway standing in for call_gateway)
# ----------------------------------------------------------------------------------------

class FakeGatewayThread:
    """A minimal real TCP AudioSocket server, run on a background thread with its own event loop,
    so the FastAPI TestClient's WebSocket (which also needs an event loop) does not conflict with it."""

    def __init__(self, reply_frames=5):
        self.reply_frames = reply_frames
        self.uuid_bytes = None
        self.frames = []
        self.port = None
        self._ready = threading.Event()
        self._loop = None
        self._server = None

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._ready.wait(timeout=5)

    def stop(self):
        """Close the server ON THE LOOP'S OWN THREAD and let serve_forever() unwind naturally, instead
        of yanking the loop to a stop. The latter leaves main()'s task permanently "pending", so its
        cleanup (closing the listening socket) only runs later via the garbage collector - on Windows'
        ProactorEventLoop that fires after the loop's IOCP proactor is already gone, producing a stray
        'Task was destroyed but it is pending!' / AttributeError on _stop_serving.
        """
        if self._loop and self._server:
            async def _shutdown():
                self._server.close()
                await self._server.wait_closed()

            future = asyncio.run_coroutine_threadsafe(_shutdown(), self._loop)
            try:
                future.result(timeout=5)
            except Exception:
                pass
        self._thread.join(timeout=5)

    def _run(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        async def handle(reader, writer):
            first = True
            try:
                t, ln = struct.unpack("!BH", await reader.readexactly(3))
                self.uuid_bytes = await reader.readexactly(ln)
                while True:
                    t, ln = struct.unpack("!BH", await reader.readexactly(3))
                    p = await reader.readexactly(ln) if ln else b""
                    if t == 0x00:
                        break
                    if t == 0x10:
                        self.frames.append(p)
                        if first:
                            first = False
                            asyncio.create_task(reply())
            except (asyncio.IncompleteReadError, ConnectionError):
                pass
            finally:
                writer.close()

        async def reply():
            pass  # payload attached below once `writer` is in scope; simplified: no AI audio needed for this test

        async def main():
            server = await asyncio.start_server(handle, "127.0.0.1", 0)
            self._server = server
            self.port = server.sockets[0].getsockname()[1]
            self._ready.set()
            async with server:
                await server.serve_forever()

        try:
            self._loop.run_until_complete(main())
        except asyncio.CancelledError:
            pass  # server.close() cancels serve_forever()'s internal future - this is the expected exit
        finally:
            # Close the loop deterministically, on the same thread that created it, rather than
            # leaving it for whenever the garbage collector happens to get to it.
            self._loop.close()


def test_full_call_over_websocket(client, monkeypatch):
    gw = FakeGatewayThread()
    gw.start()
    monkeypatch.setattr(client.server_module, "GATEWAY_PORT", gw.port)

    resp = client.post("/answer", data={"From": "+919812345678", "To": "+918065354620"})
    ws_path = "/ws?cid=" + ET.fromstring(resp.text).find("Stream").text.strip().split("cid=")[1]

    with client.websocket_connect(ws_path) as ws:
        ws.send_text(json.dumps({"event": "start", "streamId": "s1",
                                 "start": {"mediaFormat": {"encoding": "audio/x-mulaw", "sampleRate": 8000}}}))
        time.sleep(0.3)  # let the bridge connect to the fake gateway

        pcm = array.array("h", [9000] * 160).tobytes()  # 20ms of 8kHz audio
        import services.vobiz_bridge.audio as audio_mod
        ulaw = audio_mod.pcm16_to_ulaw(pcm)
        for _ in range(5):
            ws.send_text(json.dumps({"event": "media", "media": {"payload": base64.b64encode(ulaw).decode()}}))
        ws.send_text(json.dumps({"event": "stop"}))
        time.sleep(0.3)

    gw.stop()
    assert gw.uuid_bytes is not None and len(gw.uuid_bytes) == 16
    assert len(gw.frames) == 5 and all(len(f) == 320 for f in gw.frames)
    assert len(client.crm_calls) == 1
    assert client.crm_calls[0]["from_number"] == "+919812345678"
    assert client.crm_calls[0]["to_number"] == "+918065354620"


def test_websocket_with_gateway_unreachable_does_not_hang(client, monkeypatch):
    monkeypatch.setattr(client.server_module, "GATEWAY_PORT", 1)  # nothing listens here
    resp = client.post("/answer", data={"From": "+919812345678", "To": "+918065354620"})
    ws_path = "/ws?cid=" + ET.fromstring(resp.text).find("Stream").text.strip().split("cid=")[1]
    with client.websocket_connect(ws_path) as ws:
        ws.send_text(json.dumps({"event": "start", "streamId": "s1",
                                 "start": {"mediaFormat": {"encoding": "audio/x-mulaw", "sampleRate": 8000}}}))
        time.sleep(0.3)
    assert len(client.crm_calls) == 1   # CRM record is still created even though the gateway is down
