"""
Tests for the Vobiz <-> AudioSocket bridge (services/vobiz_bridge).

Run from the product folder:   python -m pytest tests/test_vobiz_bridge.py -v
(or simply:                    python tests/test_vobiz_bridge.py)

Stdlib only: a fake AudioSocket gateway (real TCP on localhost) and a fake Vobiz connection.
No Vobiz account, no ngrok, no web framework and no other service is needed.
"""
import array
import asyncio
import base64
import json
import math
import os
import struct
import sys
import tempfile
import uuid
import wave
import xml.etree.ElementTree as ET

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.vobiz_bridge import audio  # noqa: E402
from services.vobiz_bridge import bridge as vb  # noqa: E402


def tone_pcm(ms=20, hz=300, amp=9000):
    n = int(8 * ms)
    return array.array("h", [int(amp * math.sin(2 * math.pi * hz * i / 8000)) for i in range(n)]).tobytes()


def media_msg(pcm, ulaw=True):
    raw = audio.pcm16_to_ulaw(pcm) if ulaw else pcm
    return json.dumps({"event": "media", "media": {"payload": base64.b64encode(raw).decode()}})


START_MULAW = json.dumps({"event": "start", "streamId": "stream-1",
                          "start": {"mediaFormat": {"encoding": "audio/x-mulaw", "sampleRate": 8000}}})


class FakeGateway:
    """Speaks the AudioSocket protocol like services/call_gateway does."""

    def __init__(self, reply_frames=10, hangup_after=None):
        self.reply_frames, self.hangup_after = reply_frames, hangup_after
        self.uuid_bytes, self.frames, self.dtmf, self.hangups = None, [], [], 0
        self.connected = asyncio.Event()

    async def start(self):
        self.server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        self.port = self.server.sockets[0].getsockname()[1]

    async def stop(self):
        self.server.close()

    async def _handle(self, reader, writer):
        first = True
        try:
            t, ln = struct.unpack("!BH", await reader.readexactly(3))
            self.uuid_bytes = await reader.readexactly(ln)
            assert t == 0x01
            self.connected.set()
            while True:
                t, ln = struct.unpack("!BH", await reader.readexactly(3))
                p = await reader.readexactly(ln) if ln else b""
                if t == 0x00:
                    self.hangups += 1
                    break
                if t == 0x03:
                    self.dtmf.append(p)
                elif t == 0x10:
                    self.frames.append(p)
                    if first:
                        first = False
                        asyncio.create_task(self._reply(writer))
                    if self.hangup_after and len(self.frames) == self.hangup_after:
                        writer.write(struct.pack("!BH", 0x00, 0))
                        await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionError):
            pass
        finally:
            writer.close()

    async def _reply(self, writer):
        frame = tone_pcm(20)
        try:
            for _ in range(self.reply_frames):
                writer.write(struct.pack("!BH", 0x10, len(frame)) + frame)
                await writer.drain()
                await asyncio.sleep(0.005)
        except ConnectionError:
            pass


class Harness:
    """A bridge wired to a fake Vobiz connection."""

    def __init__(self, port, pending, cid_hint=None, recordings_dir=None):
        self.sent, self.ws_closed, self.crm_calls = [], 0, []

        async def send_json(m):
            self.sent.append(m)

        async def close_ws():
            self.ws_closed += 1

        async def crm_start(**kw):
            self.crm_calls.append(kw)

        self.bridge = vb.VobizCallBridge(send_json, close_ws, pending, cid_hint=cid_hint, gateway_port=port,
                                         crm_start=crm_start, recordings_dir=recordings_dir)

    async def say(self, msg):
        await self.bridge.handle_message(msg if isinstance(msg, str) else json.dumps(msg))


def new_pending(call_uuid=None, caller="+919812345678", called="+918065354620", direction="inbound"):
    p = vb.PendingCalls()
    call_uuid = call_uuid or str(uuid.uuid4())
    p.add(call_uuid, caller, called, direction, call_uuid)
    return p, call_uuid


# ----------------------------------------------------------------------------------------
# Audio codec
# ----------------------------------------------------------------------------------------

def test_mulaw_matches_the_g711_standard():
    # Known G.711 vectors (independent of any library)
    assert audio.pcm16_to_ulaw(array.array("h", [0]).tobytes()) == b"\xff"
    assert audio.pcm16_to_ulaw(array.array("h", [32767]).tobytes()) == b"\x80"
    assert audio.pcm16_to_ulaw(array.array("h", [-32768]).tobytes()) == b"\x00"
    decoded = array.array("h")
    decoded.frombytes(audio.ulaw_to_pcm16(b"\xff\x80\x00"))
    assert list(decoded) == [0, 32124, -32124]
    # A tone survives the round trip with only quantisation error
    tone = tone_pcm(100)
    back = array.array("h")
    back.frombytes(audio.ulaw_to_pcm16(audio.pcm16_to_ulaw(tone)))
    assert max(abs(a - b) for a, b in zip(array.array("h", tone), back)) < 700
    # Where the stdlib still has audioop (removed in Python 3.13), the two must agree on EVERY value
    try:
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            import audioop
    except ImportError:
        return
    every_sample = array.array("h", range(-32768, 32768)).tobytes()
    assert audio.pcm16_to_ulaw(every_sample) == audioop.lin2ulaw(every_sample, 2)
    every_code = bytes(range(256))
    assert audio.ulaw_to_pcm16(every_code) == audioop.ulaw2lin(every_code, 2)


def test_frame_slicer_and_resampler():
    data = bytes(range(256)) * 10
    for chunk in (1, 7, 160, 320, 799, 2560):
        s, frames = audio.FrameSlicer(), []
        for i in range(0, len(data), chunk):
            frames += s.push(data[i:i + chunk])
        assert all(len(f) == 320 for f in frames)
        assert b"".join(frames) + bytes(s._buf) == data
    out = array.array("h")
    out.frombytes(audio.pcm16_16k_to_8k(array.array("h", [100, 300, -100, -300]).tobytes()))
    assert list(out) == [200, -200]
    st = array.array("h")
    st.frombytes(audio.interleave_stereo(array.array("h", [1, 2]).tobytes(), array.array("h", [10, 20]).tobytes()))
    assert list(st) == [1, 10, 2, 20]


# ----------------------------------------------------------------------------------------
# Answer XML and URLs
# ----------------------------------------------------------------------------------------

def test_answer_xml_is_valid_vobizxml():
    xml = vb.build_answer_xml("wss://drool.ngrok-free.dev/ws?cid=abc", "https://drool.ngrok-free.dev/stream-status?a=1&b=2")
    root = ET.fromstring(xml)                                   # must be well-formed even with '&' in a URL
    assert root.tag == "Response" and [c.tag for c in root] == ["Stream", "Hangup"]
    stream = root[0]
    assert stream.attrib["bidirectional"] == "true" and stream.attrib["keepCallAlive"] == "true"
    assert stream.attrib["contentType"] == "audio/x-mulaw;rate=8000"
    assert stream.attrib["statusCallbackUrl"].endswith("?a=1&b=2")
    assert stream.text.strip() == "wss://drool.ngrok-free.dev/ws?cid=abc"


def test_public_url_derivation():
    ngrok = {"host": "drool.ngrok-free.dev", "x-forwarded-proto": "https"}
    assert vb.public_base_url(ngrok) == "https://drool.ngrok-free.dev"
    assert vb.public_base_url({"host": "localhost:9097"}) == "http://localhost:9097"
    assert vb.public_base_url({"host": "x.example.com"}) == "https://x.example.com"
    assert vb.public_base_url(ngrok, "https://override.example.com/") == "https://override.example.com"
    assert vb.ws_url("https://drool.ngrok-free.dev", "abc") == "wss://drool.ngrok-free.dev/ws?cid=abc"
    assert vb.ws_url("http://localhost:9097", "a b&c") == "ws://localhost:9097/ws?cid=a%20b%26c"


def test_pending_calls_matching_and_expiry():
    p = vb.PendingCalls(ttl_s=0.05)
    assert p.claim("nothing") is None
    p.add("k1", "+91111", "+91999", "inbound", "k1")
    assert p.claim("k1")["from"] == "+91111"
    assert p.claim("k1") is None                                   # a claim is single-use
    p.add("old", "+91222", "+91999")
    p.add("new", "+91333", "+91999")
    got = p.claim(None)
    assert got["from"] in ("+91222", "+91333") and got["fallback"] is True
    p.add("stale", "+91444", "+91999")
    import time
    time.sleep(0.1)
    assert p.claim("stale") is None                                # expired
    assert len(p) == 0                                             # everything has expired by now


# ----------------------------------------------------------------------------------------
# A full call
# ----------------------------------------------------------------------------------------

def test_full_call_translates_both_directions_and_records():
    async def scenario():
        gw = FakeGateway(reply_frames=12)
        await gw.start()
        pending, cid = new_pending()
        rec_dir = tempfile.mkdtemp()
        h = Harness(gw.port, pending, cid_hint=cid, recordings_dir=rec_dir)

        await h.say(START_MULAW)
        await asyncio.wait_for(gw.connected.wait(), 2)
        for _ in range(40):                                        # caller speaks 0.8 s
            await h.say(media_msg(tone_pcm(20)))
            await asyncio.sleep(0.005)
        await asyncio.sleep(0.2)
        await h.say({"event": "stop"})
        await asyncio.sleep(0.1)
        await gw.stop()

        # -> gateway: right call id, 40 exact frames, audio survives mu-law
        assert gw.uuid_bytes == uuid.UUID(cid).bytes
        assert len(gw.frames) == 40 and all(len(f) == 320 for f in gw.frames)
        sent, got = array.array("h"), array.array("h")
        sent.frombytes(tone_pcm(20))
        got.frombytes(gw.frames[5])
        assert max(abs(a - b) for a, b in zip(sent, got)) < 700

        # -> CRM: real caller / dialed number, created before the gateway saw the call
        assert h.crm_calls == [{"call_id": cid, "from_number": "+919812345678", "to_number": "+918065354620",
                                "direction": "inbound", "provider": "vobiz"}]

        # -> Vobiz: 12 playAudio events in the documented shape
        plays = [m for m in h.sent if m["event"] == "playAudio"]
        assert len(plays) == 12
        assert plays[0]["streamId"] == "stream-1"
        assert plays[0]["media"]["contentType"] == "audio/x-l16" and plays[0]["media"]["sampleRate"] == 8000
        assert len(base64.b64decode(plays[0]["media"]["payload"])) == 320

        # hang-up flows to the gateway and closes the stream
        assert gw.hangups == 1 and h.ws_closed >= 1

        # recording: stereo, 8 kHz, one frame per caller frame, both channels carry audio
        with wave.open(os.path.join(rec_dir, cid + ".wav")) as w:
            assert (w.getnchannels(), w.getframerate(), w.getsampwidth()) == (2, 8000, 2)
            assert w.getnframes() == 40 * 160
            arr = array.array("h")
            arr.frombytes(w.readframes(w.getnframes()))
        assert max(abs(x) for x in arr[0::2]) > 5000               # caller (left)
        assert max(abs(x) for x in arr[1::2]) > 5000               # AI (right)

    asyncio.run(scenario())


def test_any_chunk_size_becomes_exact_20ms_frames():
    async def scenario():
        gw = FakeGateway(reply_frames=0)
        await gw.start()
        pending, cid = new_pending()
        h = Harness(gw.port, pending, cid_hint=cid)
        await h.say(START_MULAW)
        await asyncio.wait_for(gw.connected.wait(), 2)
        total_pcm = tone_pcm(800)                                  # 800 ms = 12800 bytes = 40 frames
        ulaw = audio.pcm16_to_ulaw(total_pcm)
        pos = 0
        for size in [800, 130, 45, 800, 1, 7, 160, 3, 1000, 160] * 10:
            chunk = ulaw[pos:pos + size]
            if not chunk:
                break
            pos += len(chunk)
            await h.say({"event": "media", "media": {"payload": base64.b64encode(chunk).decode()}})
        await asyncio.sleep(0.1)
        await h.say({"event": "stop"})
        await asyncio.sleep(0.05)
        await gw.stop()
        assert pos == len(ulaw)
        assert len(gw.frames) == 40 and all(len(f) == 320 for f in gw.frames)

    asyncio.run(scenario())


def test_dtmf_reaches_the_gateway_in_both_message_shapes():
    async def scenario():
        gw = FakeGateway(reply_frames=0)
        await gw.start()
        pending, cid = new_pending()
        h = Harness(gw.port, pending, cid_hint=cid)
        await h.say(START_MULAW)
        await asyncio.wait_for(gw.connected.wait(), 2)
        await h.say({"event": "dtmf", "dtmf": {"digit": "0"}})
        await h.say({"event": "dtmf", "digit": "5"})
        await h.say({"event": "dtmf"})                              # no digit: ignored
        await asyncio.sleep(0.1)
        await h.say({"event": "stop"})
        await gw.stop()
        assert gw.dtmf == [b"0", b"5"]

    asyncio.run(scenario())


def test_gateway_ending_the_call_closes_the_vobiz_stream():
    async def scenario():
        gw = FakeGateway(reply_frames=0, hangup_after=5)
        await gw.start()
        pending, cid = new_pending()
        h = Harness(gw.port, pending, cid_hint=cid)
        await h.say(START_MULAW)
        await asyncio.wait_for(gw.connected.wait(), 2)
        for _ in range(10):
            await h.say(media_msg(tone_pcm(20)))
            await asyncio.sleep(0.01)
        await asyncio.sleep(0.1)
        await gw.stop()
        assert h.ws_closed == 1                                     # Vobiz stream closed -> <Hangup/> runs
        assert gw.hangups == 0                                      # we do not echo a hangup back

    asyncio.run(scenario())


def test_gateway_down_closes_cleanly_and_still_records_the_call():
    async def scenario():
        pending, cid = new_pending()
        h = Harness(1, pending, cid_hint=cid)                       # nothing listens on port 1
        await h.say(START_MULAW)
        await h.say(media_msg(tone_pcm(20)))                        # must not raise
        assert h.ws_closed == 1
        assert len(h.crm_calls) == 1

    asyncio.run(scenario())


def test_16khz_linear_input_is_downsampled():
    async def scenario():
        gw = FakeGateway(reply_frames=0)
        await gw.start()
        pending, cid = new_pending()
        h = Harness(gw.port, pending, cid_hint=cid)
        await h.say({"event": "start", "streamId": "s", "start": {"mediaFormat": {"encoding": "audio/x-l16", "sampleRate": 16000}}})
        await asyncio.wait_for(gw.connected.wait(), 2)
        pcm16k = array.array("h", [100, 300] * 160).tobytes()       # 20 ms at 16 kHz = 320 samples
        await h.say({"event": "media", "media": {"payload": base64.b64encode(pcm16k).decode()}})
        await asyncio.sleep(0.1)
        await h.say({"event": "stop"})
        await gw.stop()
        assert len(gw.frames) == 1
        out = array.array("h")
        out.frombytes(gw.frames[0])
        assert set(out) == {200}

    asyncio.run(scenario())


def test_media_before_start_and_duplicate_start_are_harmless():
    async def scenario():
        gw = FakeGateway(reply_frames=0)
        await gw.start()
        pending, cid = new_pending()
        h = Harness(gw.port, pending, cid_hint=cid)
        await h.say(media_msg(tone_pcm(20)))                        # before start: ignored
        await h.say("this is not json")                             # ignored
        await h.say(START_MULAW)
        await asyncio.wait_for(gw.connected.wait(), 2)
        await h.say(START_MULAW)                                    # duplicate: ignored
        await asyncio.sleep(0.05)
        await h.say({"event": "stop"})
        await gw.stop()
        assert len(h.crm_calls) == 1 and h.bridge.frames_from_caller == 0

    asyncio.run(scenario())


def test_unmatched_stream_and_non_uuid_vobiz_ids():
    async def scenario():
        gw = FakeGateway(reply_frames=0)
        await gw.start()
        # no /answer details at all
        h = Harness(gw.port, vb.PendingCalls())
        await h.say(START_MULAW)
        await asyncio.wait_for(gw.connected.wait(), 2)
        assert h.crm_calls[0]["from_number"] == "unknown"
        assert vb.as_uuid(h.crm_calls[0]["call_id"])
        await h.say({"event": "stop"})

        # Vobiz id that is not a UUID -> we generate one but still use the real numbers
        gw2 = FakeGateway(reply_frames=0)
        await gw2.start()
        p = vb.PendingCalls()
        p.add("MA_12345", "+919000000001", "+918065354620", "inbound", "MA_12345")
        h2 = Harness(gw2.port, p, cid_hint="MA_12345")
        await h2.say(START_MULAW)
        await asyncio.wait_for(gw2.connected.wait(), 2)
        assert h2.crm_calls[0]["from_number"] == "+919000000001"
        assert h2.crm_calls[0]["call_id"] != "MA_12345" and vb.as_uuid(h2.crm_calls[0]["call_id"])
        await h2.say({"event": "stop"})
        await gw.stop()
        await gw2.stop()

    asyncio.run(scenario())


def test_outbound_call_direction_is_passed_through_and_recording_dir_is_created():
    async def scenario():
        gw = FakeGateway(reply_frames=0)
        await gw.start()
        pending, cid = new_pending(caller="+918065354620", called="+919812345678", direction="outbound")
        rec = os.path.join(tempfile.mkdtemp(), "nested", "recordings")
        h = Harness(gw.port, pending, cid_hint=cid, recordings_dir=rec)
        await h.say(START_MULAW)
        await asyncio.wait_for(gw.connected.wait(), 2)
        await h.say(media_msg(tone_pcm(20)))
        await h.say({"event": "stop"})
        await gw.stop()
        assert h.crm_calls[0]["direction"] == "outbound"
        assert os.path.exists(os.path.join(rec, cid + ".wav"))

    asyncio.run(scenario())


if __name__ == "__main__":                                         # plain runner, no pytest needed
    import traceback
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print("PASS", name)
        except Exception:
            failed += 1
            print("FAIL", name)
            traceback.print_exc()
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
