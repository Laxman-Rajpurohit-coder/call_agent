#!/usr/bin/env python3
"""
Phone-free test call.

Plays WAV file(s) into the call gateway over the AudioSocket protocol - exactly what Asterisk does -
waits for the AI to answer each one, optionally presses a DTMF key, hangs up, and (optionally) checks
that the call landed in the CRM.  No Vobiz, no Asterisk, no phone needed.

    python tools/dev/audiosocket_test_call.py --wav path/to/human_transfer_001.wav
    python tools/dev/audiosocket_test_call.py --wav a.wav --wav b.wav --check-crm http://127.0.0.1:9090
    python tools/dev/audiosocket_test_call.py --dtmf 0            # press 0 (human handoff), no speech

Because there is no Asterisk, the gateway runs in "DIRECT" mode and cannot know a caller number.  Set
    TEST_CALLER_NUMBER=+919812345678
in the GATEWAY's environment (.env) if you want the call attributed to a specific contact.

Exit code: 0 = every turn got an AI reply (and the CRM check, if requested, passed)
           1 = the AI stayed silent on a turn, or the CRM check failed
           2 = could not start (gateway unreachable, or a WAV file could not be read)
"""
import argparse
import array
import asyncio
import json
import struct
import sys
import time
import urllib.error
import urllib.request
import uuid
import wave

FRAME_BYTES = 320          # 160 samples x 16-bit = 20 ms of 8 kHz mono
FRAME_S = 0.020
T_HANGUP, T_UUID, T_DTMF, T_AUDIO, T_ERROR = 0x00, 0x01, 0x03, 0x10, 0xFF


# --------------------------------------------------------------------------------------
# WAV -> 8 kHz mono 16-bit PCM (stdlib only)
# --------------------------------------------------------------------------------------

def load_wav_8k_mono(path, gain=1.0, normalize=False):
    try:
        with wave.open(path, "rb") as w:
            channels, width, rate, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
            raw = w.readframes(n)
    except wave.Error as ex:
        raise ValueError(f"{path}: {ex}. Convert it first:  ffmpeg -i in.wav -ar 8000 -ac 1 -sample_fmt s16 out.wav")

    if width == 2:
        samples = array.array("h")
        samples.frombytes(raw)
        if sys.byteorder == "big":
            samples.byteswap()
    elif width == 1:                                   # 8-bit WAV is unsigned
        samples = array.array("h", [(b - 128) << 8 for b in raw])
    else:
        raise ValueError(f"{path}: {width * 8}-bit WAV is not supported (use 16-bit PCM)")

    if channels > 1:                                   # mix down to mono
        samples = array.array("h", [
            int(sum(samples[i:i + channels]) / channels)
            for i in range(0, len(samples) - channels + 1, channels)
        ])

    if rate != 8000:
        ratio = rate / 8000.0
        n_out = int(len(samples) / ratio)
        out = array.array("h")
        if ratio > 1:                                  # downsample: box filter (cheap anti-aliasing)
            for i in range(n_out):
                a = int(i * ratio)
                b = max(a + 1, int((i + 1) * ratio))
                seg = samples[a:b]
                out.append(int(sum(seg) / len(seg)))
        else:                                          # upsample: linear interpolation
            for i in range(n_out):
                pos = i * ratio
                i0 = int(pos)
                s0, s1 = samples[i0], samples[min(i0 + 1, len(samples) - 1)]
                out.append(int(s0 + (s1 - s0) * (pos - i0)))
        samples = out

    peak = max((abs(s) for s in samples), default=0)
    if normalize and peak > 0:
        gain = 16000.0 / peak
    if gain != 1.0:
        samples = array.array("h", [max(-32768, min(32767, int(s * gain))) for s in samples])
        peak = max((abs(s) for s in samples), default=0)
    if peak < 300:
        print(f"  ! {path}: peak level {peak} is below the gateway's noise gate (300) - it will be discarded. "
              f"Use --normalize or --gain.")

    pcm = samples.tobytes() if sys.byteorder == "little" else (samples.byteswap() or samples.tobytes())
    if len(pcm) % FRAME_BYTES:
        pcm += b"\x00" * (FRAME_BYTES - len(pcm) % FRAME_BYTES)
    return pcm


def save_wav_8k(path, pcm):
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(bytes(pcm))


# --------------------------------------------------------------------------------------
# AudioSocket call
# --------------------------------------------------------------------------------------

class TestCall:
    def __init__(self, reader, writer):
        self.reader, self.writer = reader, writer
        self.ai_bytes = 0
        self.ai_audio = bytearray()
        self.last_ai_ts = 0.0
        self.closed = False
        self._next_send = time.monotonic()

    async def receive_loop(self):
        try:
            while True:
                t, ln = struct.unpack("!BH", await self.reader.readexactly(3))
                payload = await self.reader.readexactly(ln) if ln else b""
                if t == T_AUDIO:
                    self.ai_bytes += len(payload)
                    self.ai_audio += payload
                    self.last_ai_ts = time.monotonic()
                elif t == T_HANGUP:
                    break
        except (asyncio.IncompleteReadError, ConnectionError, OSError):
            pass
        self.closed = True

    async def _send(self, type_byte, payload=b""):
        self.writer.write(struct.pack("!BH", type_byte, len(payload)) + payload)
        await self.writer.drain()

    async def send_frame(self, frame):
        """One 20 ms frame, paced against a monotonic clock (like Asterisk does)."""
        now = time.monotonic()
        if self._next_send < now - 0.2:                 # we fell behind: do not burst
            self._next_send = now
        delay = self._next_send - now
        if delay > 0:
            await asyncio.sleep(delay)
        await self._send(T_AUDIO, frame)
        self._next_send += FRAME_S

    async def send_pcm(self, pcm):
        for i in range(0, len(pcm), FRAME_BYTES):
            if self.closed:
                return
            await self.send_frame(pcm[i:i + FRAME_BYTES])

    async def silence_until(self, predicate, timeout):
        """Keep the line alive with silence until predicate() is true. Returns False on timeout."""
        deadline = time.monotonic() + timeout
        silence = b"\x00" * FRAME_BYTES
        while time.monotonic() < deadline and not self.closed:
            if predicate():
                return True
            await self.send_frame(silence)
        return predicate()

    def ai_quiet_for(self, seconds):
        return self.last_ai_ts > 0 and (time.monotonic() - self.last_ai_ts) >= seconds

    async def wait_for_ai_turn(self, bytes_before, start_timeout, quiet_s):
        """Wait until the AI starts speaking, then until it has been quiet for quiet_s."""
        started = await self.silence_until(lambda: self.ai_bytes > bytes_before, start_timeout)
        if not started:
            return False
        await self.silence_until(lambda: self.ai_quiet_for(quiet_s), 40.0)
        return True


async def run_call(args):
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(args.host, args.port), 5)
    except (OSError, asyncio.TimeoutError) as ex:
        print(f"Cannot connect to the gateway at {args.host}:{args.port}: {ex}")
        print("Is `python start_services.py` (or the call_gateway) running?")
        return 2, None

    call_id = args.call_id or str(uuid.uuid4())
    call = TestCall(reader, writer)
    receiver = asyncio.create_task(call.receive_loop())
    await call._send(T_UUID, uuid.UUID(call_id).bytes)
    print(f"Connected. call_id={call_id}")

    ok = True
    t0 = time.monotonic()

    # 1. The gateway greets on the first audio frame. Stay silent until the greeting is finished,
    #    otherwise our speech would (correctly) trigger barge-in and cut the greeting off.
    before = call.ai_bytes
    greeted = await call.wait_for_ai_turn(before, args.reply_timeout, args.quiet)
    print(f"  greeting: {'heard %.1fs of AI audio' % (call.ai_bytes / 16000.0) if greeted else 'NOT heard'}")

    # 2. One turn per --wav
    for n, (path, pcm) in enumerate(zip(args.wav, args.pcms), 1):
        before = call.ai_bytes
        print(f"  turn {n}: speaking {len(pcm) / 16000.0:.1f}s from {path}")
        await call.send_pcm(pcm)
        replied = await call.wait_for_ai_turn(before, args.reply_timeout, args.quiet)
        got = call.ai_bytes - before
        if replied:
            print(f"          AI replied with {got / 16000.0:.1f}s of audio")
        else:
            print(f"          AI did NOT reply within {args.reply_timeout:.0f}s")
            ok = False
        if call.closed:
            print("          (the gateway closed the call)")
            break

    # 3. Optional keypad press (0 = human handoff)
    if args.dtmf and not call.closed:
        print(f"  pressing DTMF '{args.dtmf}'")
        await call._send(T_DTMF, args.dtmf[0].encode("ascii"))
        await call.silence_until(lambda: call.closed, 4.0)

    # 4. Hang up like Asterisk does and give the gateway time to write the CRM record
    if not call.closed:
        try:
            await call._send(T_HANGUP)
        except OSError:
            pass
    await asyncio.sleep(1.0)
    try:
        writer.close()
        await writer.wait_closed()
    except Exception:
        pass
    receiver.cancel()

    if args.save_ai and call.ai_audio:
        save_wav_8k(args.save_ai, call.ai_audio)
        print(f"  AI audio saved to {args.save_ai}")
    print(f"Call finished after {time.monotonic() - t0:.1f}s; AI spoke {call.ai_bytes / 16000.0:.1f}s in total.")
    return (0 if ok else 1), call_id


# --------------------------------------------------------------------------------------
# CRM check
# --------------------------------------------------------------------------------------

def _get_json(url):
    with urllib.request.urlopen(url, timeout=5) as r:
        return json.load(r)


def check_crm(base_url, call_id, wait_s, analysis_wait_s):
    url = f"{base_url.rstrip('/')}/api/v1/calls/{call_id}"
    print(f"\nChecking the CRM: {url}")
    data, deadline = None, time.time() + wait_s
    while time.time() < deadline:
        try:
            data = _get_json(url)
            if str(data.get("status", "")).lower() == "completed":
                break
        except urllib.error.HTTPError as ex:
            if ex.code in (401, 403):
                print("  The dashboard requires a login for this endpoint - check the call in the CRM screen instead.")
                return None
            data = None                                  # 404: gateway has not written it yet
        except OSError as ex:
            print(f"  Dashboard not reachable: {ex}")
            return False
        time.sleep(1.0)

    if not data:
        print("  FAIL: no call record appeared. The gateway did not write to the CRM "
              "(look for CRM_CALL_STARTED / 'start_call failed' in call_gateway.log).")
        return False

    if analysis_wait_s:
        print(f"  waiting {analysis_wait_s}s for the post-call analysis ...")
        time.sleep(analysis_wait_s)
        try:
            data = _get_json(url)
        except Exception:
            pass

    transcript = data.get("transcript") or []
    users = [t for t in transcript if isinstance(t, dict) and t.get("role") == "user"]
    print(f"  status={data.get('status')}  duration_s={data.get('duration_s')}  from={data.get('from_number')}  "
          f"provider={data.get('provider')}")
    print(f"  transcript turns={len(transcript)} (caller turns={len(users)})  recording_url={data.get('recording_url')}")
    for key in ("handoff_reason", "analysis_status", "ai_summary"):
        if data.get(key) is not None:
            print(f"  {key}={data.get(key)}")
    for it in (data.get("interactions") or []):
        print(f"  interaction: intent={it.get('intent_detected')} lead_label={it.get('lead_label')} "
              f"confidence={it.get('confidence')} quote={it.get('evidence_quote')!r}")
    passed = str(data.get("status", "")).lower() == "completed" and len(transcript) > 0
    print("  " + ("PASS: the call is in the CRM with a transcript." if passed else "FAIL: call recorded but incomplete."))
    return passed


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="Phone-free test call into the AudioSocket gateway.")
    ap.add_argument("--wav", action="append", default=[], help="WAV file to speak (repeat for several turns)")
    ap.add_argument("--dtmf", help="keypad digit to press after the turns, e.g. 0 for human handoff")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=9092)
    ap.add_argument("--call-id", help="UUID to use (default: random)")
    ap.add_argument("--gain", type=float, default=1.0, help="multiply the volume")
    ap.add_argument("--normalize", action="store_true", help="scale each WAV to a healthy telephone level")
    ap.add_argument("--reply-timeout", type=float, default=20.0, help="seconds to wait for the AI to start replying")
    ap.add_argument("--quiet", type=float, default=1.2, help="seconds of AI silence that count as 'finished'")
    ap.add_argument("--save-ai", help="save everything the AI said to this WAV file")
    ap.add_argument("--check-crm", metavar="URL", help="dashboard URL, e.g. http://127.0.0.1:9090")
    ap.add_argument("--crm-wait", type=float, default=25.0)
    ap.add_argument("--analysis-wait", type=float, default=10.0, help="seconds to let the post-call analysis run")
    args = ap.parse_args()
    if not args.wav and not args.dtmf:
        ap.error("give at least one --wav or a --dtmf")

    args.pcms = []
    try:
        for path in args.wav:
            args.pcms.append(load_wav_8k_mono(path, args.gain, args.normalize))
    except (ValueError, OSError) as ex:
        print(f"Cannot read the audio: {ex}")
        sys.exit(2)

    code, call_id = asyncio.run(run_call(args))
    if code == 2:
        sys.exit(2)
    if args.check_crm:
        crm_ok = check_crm(args.check_crm, call_id, args.crm_wait, args.analysis_wait)
        if crm_ok is False:
            code = code or 1
    print("\nRESULT: " + ("PASS" if code == 0 else "FAIL"))
    sys.exit(code)


if __name__ == "__main__":
    main()
