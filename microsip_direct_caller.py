import os
import sys
import socket
import time
import uuid
import json
import random
import asyncio
import audioop
import numpy as np
import httpx
import re
from datetime import datetime

try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

# ⚡ WINDOWS HIGH-PRECISION MULTIMEDIA TIMER (1ms Resolution)
# Forces Windows thread scheduler timer resolution from 15.6ms down to 1.0ms.
# Eliminates softphone jitter underruns, buzzing artifacts, and mid-sentence pauses.
try:
    import ctypes
    ctypes.windll.winmm.timeBeginPeriod(1)
except Exception:
    pass

ROOT_DIR = r"c:\daily_works\superfone_call"
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from services.dashboard.app.services.script_engine import ScriptEngine
from services.dashboard.app.database import SessionLocal
from services.dashboard.app.models import CallSession, CallInteraction, Organization
try:
    from path_c_hybrid_agent.config import GROQ_API_KEY, DEEPGRAM_API_KEY
    from path_c_hybrid_agent.llm_groq import normalize_phonetics_for_tts
except Exception:
    GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
    DEEPGRAM_API_KEY = os.environ.get("DEEPGRAM_API_KEY", "")
    def normalize_phonetics_for_tts(text: str) -> str: return text

STT_URL = "http://127.0.0.1:9094/stt"
TTS_URL = "http://127.0.0.1:9095/tts"

def log_gateway_event(msg: str):
    try:
        log_file = r"c:\daily_works\superfone_call\call_gateway.log"
        ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S,%f")[:-3]
        line = f"{ts} - INFO - {msg}\n"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass


MICROSIP_IP = "127.0.0.1"
MICROSIP_PORT = 5060 # MicroSIP primary listening UDP port
SIP_BIND_PORT = 5066 # Local sender port
RTP_BIND_PORT = 9098 # Local RTP socket port (free from 9092)

import subprocess

def detect_microsip_udp_ports() -> list[int]:
    """Dynamically detects ALL active UDP listening ports of MicroSIP.exe using netstat"""
    ports = []
    try:
        res = subprocess.run(["cmd", "/c", "tasklist /fo csv"], capture_output=True, text=True)
        pid = None
        for line in res.stdout.splitlines():
            if "microsip.exe" in line.lower():
                parts = [p.strip('"') for p in line.split(',')]
                if len(parts) >= 2 and parts[1].isdigit():
                    pid = parts[1]
                    break
        if not pid:
            print("[MicroSIP Auto-Launcher] MicroSIP softphone is not running. Launching on Desktop...", flush=True)
            microsip_exe = r"c:\daily_works\superfone_call\MicroSIP-3.22.12\MicroSIP.exe"
            subprocess.run(["powershell", "-Command", f"Start-Process '{microsip_exe}'"], capture_output=True)
            time.sleep(2.0)
            res = subprocess.run(["cmd", "/c", "tasklist /fo csv"], capture_output=True, text=True)
            for line in res.stdout.splitlines():
                if "microsip.exe" in line.lower():
                    parts = [p.strip('"') for p in line.split(',')]
                    if len(parts) >= 2 and parts[1].isdigit():
                        pid = parts[1]
                        break

        if pid:
            res_net = subprocess.run(["cmd", "/c", f"netstat -ano | findstr {pid}"], capture_output=True, text=True)
            for line in res_net.stdout.splitlines():
                if "UDP" in line:
                    parts = line.split()
                    if len(parts) >= 2:
                        addr = parts[1]
                        if ":" in addr:
                            port_str = addr.split(":")[-1]
                            if port_str.isdigit():
                                port = int(port_str)
                                if port not in ports:
                                    ports.append(port)
    except Exception as ex:
        print(f"Dynamic Port Scanner warning: {ex}")
    
    if 5060 not in ports:
        ports.append(5060)
    return ports

class MicroSIPDirectCaller:
    def __init__(self):
        self.sip_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Bind to ephemeral port 0 so Windows OS guarantees a 100% fresh, unblocked local socket for every call
        try:
            self.sip_sock.bind(("127.0.0.1", 0))
        except Exception:
            self.sip_sock.bind(("0.0.0.0", 0))
        
        self.local_port = self.sip_sock.getsockname()[1]
        self.sip_sock.settimeout(5.0)
        self.call_id = f"sf-call-{uuid.uuid4().hex[:10]}"
        self.from_tag = f"sf-{uuid.uuid4().hex[:6]}"
        self.to_tag = ""
        self.rtp_port = RTP_BIND_PORT
        self.remote_rtp_port = 5062
        self.target_addr = None
        self.is_answered = False
        self.recording_pcm = bytearray()

    def build_sdp(self):
        return (
            "v=0\r\n"
            f"o=Superfone 1000 1000 IN IP4 127.0.0.1\r\n"
            "s=Superfone AI Voice Agent Call\r\n"
            "c=IN IP4 127.0.0.1\r\n"
            "t=0 0\r\n"
            f"m=audio {self.rtp_port} RTP/AVP 0 101\r\n"
            "a=rtpmap:0 PCMU/8000\r\n"
            "a=rtpmap:101 telephone-event/8000\r\n"
            "a=fmtp:101 0-16\r\n"
            "a=sendrecv\r\n"
        )

    async def send_bye(self):
        """Sends a SIP BYE message to MicroSIP to gracefully terminate the call and reset softphone state to IDLE"""
        target = self.target_addr or (MICROSIP_IP, 5060)
        bye_msg = (
            f"BYE sip:test1000@{MICROSIP_IP}:{target[1]} SIP/2.0\r\n"
            f"Via: SIP/2.0/UDP 127.0.0.1:{self.local_port};branch=z9hG4bK-{uuid.uuid4().hex[:8]}\r\n"
            f"From: \"Superfone AI Agent\" <sip:700@127.0.0.1:{self.local_port}>;tag={self.from_tag}\r\n"
            f"To: <sip:test1000@{MICROSIP_IP}:{target[1]}>;tag={self.to_tag}\r\n"
            f"Call-ID: {self.call_id}@{MICROSIP_IP}\r\n"
            f"CSeq: 2 BYE\r\n"
            f"Max-Forwards: 70\r\n"
            f"User-Agent: Superfone-AI-Platform/2.0\r\n"
            f"Content-Length: 0\r\n\r\n"
        )
        print(f"🔚 [SIP SIGNALING] Transmitting SIP BYE to MicroSIP at {target} -> Softphone dialog reset to IDLE!")
        for _ in range(3):
            try:
                self.sip_sock.sendto(bye_msg.encode("utf-8"), target)
            except Exception:
                pass
            await asyncio.sleep(0.02)

    async def trigger_microsip_ring(self):
        detected = detect_microsip_udp_ports()
        target_ports = list(set([5060] + detected))
        target_port = target_ports[0]

        sdp = self.build_sdp()
        content_length = len(sdp)
        
        print("=" * 70)
        print("  SUPERFONE AI VOICE PLATFORM — MICROSIP DIRECT TELEPHONY CALL")
        print("=" * 70)
        print(f"📲 Sending SIP INVITE from local UDP port {self.local_port} to MicroSIP ports {target_ports}...")
        print("🔔 [MICROSIP IS RINGING ON YOUR DESKTOP SCREEN!]")
        print("👉 CLICK 'ANSWER' ON YOUR MICROSIP WINDOW TO CONNECT THE AGENT!")
        print("=" * 70)

        invite = (
            f"INVITE sip:test1000@{MICROSIP_IP}:{target_port} SIP/2.0\r\n"
            f"Via: SIP/2.0/UDP 127.0.0.1:{self.local_port};branch=z9hG4bK-{uuid.uuid4().hex[:8]};rport\r\n"
            f"From: \"Superfone AI Agent\" <sip:700@127.0.0.1:{self.local_port}>;tag={self.from_tag}\r\n"
            f"To: <sip:test1000@{MICROSIP_IP}:{target_port}>\r\n"
            f"Call-ID: {self.call_id}@{MICROSIP_IP}\r\n"
            f"CSeq: 1 INVITE\r\n"
            f"Contact: <sip:700@127.0.0.1:{self.local_port}>\r\n"
            f"Max-Forwards: 70\r\n"
            f"User-Agent: Superfone-AI-Platform/2.0\r\n"
            f"Content-Type: application/sdp\r\n"
            f"Content-Length: {content_length}\r\n"
            f"\r\n"
            f"{sdp}"
        )
        
        self.sip_sock.settimeout(0.05)
        for _ in range(3):
            for p in target_ports:
                try:
                    self.sip_sock.sendto(invite.encode("utf-8"), (MICROSIP_IP, p))
                except Exception:
                    pass
            await asyncio.sleep(0.02)

        t0 = time.time()
        max_timeout = 25.0
        while time.time() - t0 < max_timeout:
            try:
                data, addr = self.sip_sock.recvfrom(4096)
                msg = data.decode("utf-8", errors="ignore")
                
                if "180 Ringing" in msg:
                    print("🔔 MicroSIP Status: RINGING...")
                    max_timeout = 45.0  # Give user 45s window to click Answer when softphone rings
                elif "200 OK" in msg:
                    print("✅ USER CLICKED ANSWER ON MICROSIP! CONNECTING MEDIA STREAM...")
                    self.is_answered = True
                    self.target_addr = addr
                    for line in msg.splitlines():
                        if line.startswith("To:") and "tag=" in line:
                            self.to_tag = line.split("tag=")[1].strip()
                        if line.startswith("m=audio"):
                            try:
                                self.remote_rtp_port = int(line.split()[1])
                            except Exception:
                                self.remote_rtp_port = 5062
                    
                    ack = (
                        f"ACK sip:test1000@{MICROSIP_IP}:{addr[1]} SIP/2.0\r\n"
                        f"Via: SIP/2.0/UDP 127.0.0.1:{self.local_port};branch=z9hG4bK-{uuid.uuid4().hex[:8]}\r\n"
                        f"From: \"Superfone AI Agent\" <sip:700@127.0.0.1:{self.local_port}>;tag={self.from_tag}\r\n"
                        f"To: <sip:test1000@{MICROSIP_IP}:{addr[1]}>;tag={self.to_tag}\r\n"
                        f"Call-ID: {self.call_id}@{MICROSIP_IP}\r\n"
                        f"CSeq: 1 ACK\r\n"
                        f"Max-Forwards: 70\r\n"
                        f"Content-Length: 0\r\n\r\n"
                    )
                    for _ in range(3):
                        self.sip_sock.sendto(ack.encode("utf-8"), (MICROSIP_IP, addr[1]))
                        await asyncio.sleep(0.01)
                    break
            except (socket.timeout, ConnectionResetError, OSError):
                pass
            await asyncio.sleep(0.02)

        if not self.is_answered:
            print("⏱️ Timed out waiting for MicroSIP connection (45s max timeout).")

def downsample_to_8k(pcm_bytes: bytes, native_sr: int = 24000) -> bytes:
    """
    Downsamples 24kHz / 16kHz PCM audio to 8,000Hz PCMU Telephony standard
    using anti-aliasing sinc interpolation to eliminate robotic/metallic static.
    """
    if not pcm_bytes:
        return b""
    if len(pcm_bytes) % 2 != 0:
        pcm_bytes = pcm_bytes[:-1]
    samples = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32)
    if len(samples) == 0:
        return b""
    
    if native_sr == 8000:
        return pcm_bytes

    try:
        from scipy import signal
        gcd = int(np.gcd(native_sr, 8000))
        up = 8000 // gcd
        down = native_sr // gcd
        resampled = signal.resample_poly(samples, up, down)
    except Exception:
        num_out = int(len(samples) * 8000 / native_sr)
        resampled = np.interp(np.linspace(0, len(samples), num_out), np.arange(len(samples)), samples)
        
    return np.clip(resampled, -32768, 32767).astype(np.int16).tobytes()

def ensure_8k_pcm(raw_audio_bytes: bytes, assumed_sr: int = 24000) -> bytes:
    """
    Guarantees 24kHz / 16kHz TTS PCM is downsampled to 8,000Hz Telephony PCM
    using anti-aliased sinc interpolation to eliminate robotic/metallic buzzes.
    """
    if not raw_audio_bytes:
        return b""
    if len(raw_audio_bytes) % 2 != 0:
        raw_audio_bytes = raw_audio_bytes[:-1]
    
    samples = np.frombuffer(raw_audio_bytes, dtype=np.int16).astype(np.float32)
    if len(samples) == 0:
        return b""

    if assumed_sr == 8000:
        return raw_audio_bytes

    try:
        from scipy import signal
        gcd = int(np.gcd(assumed_sr, 8000))
        up = 8000 // gcd
        down = assumed_sr // gcd
        resampled = signal.resample_poly(samples, up, down)
    except Exception:
        num_out = int(len(samples) * 8000 / assumed_sr)
        resampled = np.interp(np.linspace(0, len(samples), num_out), np.arange(len(samples)), samples)

    return np.clip(resampled, -32768, 32767).astype(np.int16).tobytes()

async def send_rtp_audio(rtp_sock, remote_port, raw_audio_bytes, chunk_size=160, check_barge_in=True, native_sr=24000):
    """
    Sends u-law RTP audio packets over UDP with monotonic clock-jitter compensation and Barge-In detection.
    Automatically resamples 24kHz / 16kHz PCM down to 8,000Hz PCMU Telephony standard.
    """
    ports_to_send = {remote_port if remote_port else 5062}
    if _active_caller_instance and hasattr(_active_caller_instance, "dynamic_rtp_port") and _active_caller_instance.dynamic_rtp_port:
        ports_to_send.add(_active_caller_instance.dynamic_rtp_port)

    rtp_sock.settimeout(0.0005)

    # 1. Resample native 24kHz / 16kHz PCM down to 8,000Hz 16-bit Mono PCM
    pcm_8k = ensure_8k_pcm(raw_audio_bytes, assumed_sr=native_sr)
    
    # 2. Convert 8kHz PCM to G.711 u-law
    try:
        ulaw_bytes = audioop.lin2ulaw(pcm_8k, 2)
    except Exception:
        ulaw_bytes = pcm_8k

    seq = random.randint(1000, 50000)
    timestamp = random.randint(10000, 500000)
    ssrc = 0x12345678
    
    t_start = time.perf_counter()
    num_chunks = len(ulaw_bytes) // chunk_size
    barge_in_triggered = False
    barge_in_counter = 0
    for idx in range(num_chunks):
        # ⚡ BARGE-IN CHECK: Inspect incoming socket data AFTER 25 chunks (500ms) to avoid false click trips
        if check_barge_in and idx >= 25 and idx % 2 == 0:
            try:
                rx_pkt, rx_addr = rtp_sock.recvfrom(2048)
                if rx_addr and len(rx_addr) >= 2 and _active_caller_instance:
                    _active_caller_instance.dynamic_rtp_port = rx_addr[1]
                if len(rx_pkt) > 12:
                    rx_pcm = audioop.ulaw2lin(rx_pkt[12:], 2)
                    rms_val = audioop.rms(rx_pcm, 2)
                    if rms_val > 3500: # High threshold for intentional loud mic speech interruption
                        barge_in_counter += 1
                        if barge_in_counter >= 3:
                            print(f"\n🛑 [TRUE BARGE-IN DETECTED] User interrupted AI speech (RMS={rms_val})! Stopping audio playback.")
                            barge_in_triggered = True
                            break
                    else:
                        barge_in_counter = max(0, barge_in_counter - 1)
            except (socket.timeout, ConnectionResetError, OSError):
                pass

        i = idx * chunk_size
        chunk = ulaw_bytes[i:i+chunk_size]
        
        # Build 12-byte standard RFC 3550 RTP Header
        header = bytearray(12)
        header[0] = 0x80 # V=2, P=0, X=0, CC=0
        header[1] = 0x00 # Payload Type 0 = PCMU (u-law 8kHz)
        header[2] = (seq >> 8) & 0xff
        header[3] = seq & 0xff
        header[4] = (timestamp >> 24) & 0xff
        header[5] = (timestamp >> 16) & 0xff
        header[6] = (timestamp >> 8) & 0xff
        header[7] = timestamp & 0xff
        header[8] = (ssrc >> 24) & 0xff
        header[9] = (ssrc >> 16) & 0xff
        header[10] = (ssrc >> 8) & 0xff
        header[11] = ssrc & 0xff

        rtp_pkt = bytes(header) + chunk
        if _active_caller_instance and hasattr(_active_caller_instance, "recording_pcm"):
            try:
                _active_caller_instance.recording_pcm.extend(audioop.ulaw2lin(chunk, 2))
            except Exception:
                pass

        for p_target in ports_to_send:
            try:
                rtp_sock.sendto(rtp_pkt, (MICROSIP_IP, p_target))
            except Exception:
                pass
        
        seq = (seq + 1) & 0xFFFF
        timestamp = (timestamp + 160) & 0xFFFFFFFF
        
        # High-precision sub-millisecond monotonic timer pacing to eliminate Windows clock tick jitter
        target_time = t_start + ((idx + 1) * 0.020)
        time_to_wait = target_time - time.perf_counter()
        if time_to_wait > 0.002:
            await asyncio.sleep(time_to_wait - 0.001)
        while time.perf_counter() < target_time:
            pass # Precise spinlock for exact 20.000ms UDP frame delivery!
            
    return barge_in_triggered

async def speak_text_to_microsip(rtp_sock, remote_port, text, voice="aura-asteria-en", check_barge_in=True):
    text = normalize_phonetics_for_tts(text)
    print(f"\n🤖 AI AGENT SPEAKING INTO MICROSIP [{voice}]: \"{text}\"")
    
    # ⚡ 1. PRIMARY ULTRA-FAST DEEPGRAM AURA NEURAL TTS (~200ms LATENCY, 0ms FFMPEG OVERHEAD)
    try:
        from path_c_hybrid_agent.config import DEEPGRAM_API_KEY
        if DEEPGRAM_API_KEY:
            url = "https://api.deepgram.com/v1/speak?model=aura-asteria-en&encoding=linear16&sample_rate=24000"
            headers = {"Authorization": f"Token {DEEPGRAM_API_KEY}", "Content-Type": "application/json"}
            async with httpx.AsyncClient() as client:
                resp = await client.post(url, headers=headers, json={"text": text}, timeout=3.0)
                if resp.status_code == 200 and len(resp.content) > 44:
                    raw_pcm_24k = resp.content[44:] if resp.content.startswith(b"RIFF") else resp.content
                    await send_rtp_audio(rtp_sock, remote_port, raw_pcm_24k, native_sr=24000, check_barge_in=check_barge_in)
                    return
    except Exception as ex:
        print(f"Deepgram Aura synthesis notice: {ex}")

    # ⚡ 2. IN-MEMORY NEURAL TTS FALLBACK
    try:
        from path_c_hybrid_agent.tts_cartesia import generate_inmemory_neural_pcm
        pcm_24k = await generate_inmemory_neural_pcm(text, lang='hi')
        if pcm_24k and len(pcm_24k) > 0:
            await send_rtp_audio(rtp_sock, remote_port, pcm_24k, native_sr=24000, check_barge_in=check_barge_in)
            return
    except Exception as ex:
        print(f"In-memory synthesis notice: {ex}")

_active_caller_instance = None

async def run_microsip_session(campaign_id: str = None, script_content: str = None, voice_model: str = None, call_mode: str = "AUTO", system_prompt: str = None):
    global _active_caller_instance
    if _active_caller_instance:
        print("⚡ [NEW CALL DISPATCH] Automatically terminating previous active call session...")
        try:
            await _active_caller_instance.send_bye()
        except Exception:
            pass
        await asyncio.sleep(0.3)

    raw_script = script_content.strip() if script_content else ""
    voice = voice_model or "deepgram_aura_asteria"
    target_phone = "test1000"

    # Explicit Mode Determination:
    if call_mode == "INTERACTIVE_AI":
        is_interactive = True
    elif call_mode == "SCRIPT":
        is_interactive = False
    else:
        # AUTO mode logic: Interactive ONLY if raw_script is empty or system_prompt is provided
        is_interactive = not bool(raw_script) or bool(system_prompt and system_prompt.strip())

    # If Interactive AI Mode, force raw_script to empty so it NEVER recites any script text!
    if is_interactive:
        raw_script = ""

    # DB Query for campaign details (phone number, voice model)
    if campaign_id:
        db = SessionLocal()
        try:
            from services.dashboard.app.models import Campaign, CampaignContact, Contact
            camp = db.query(Campaign).filter(Campaign.id == campaign_id).first()
            if camp:
                # If explicit campaign type is set in DB, enforce it!
                c_type = getattr(camp, "type", None)
                if c_type == "INTERACTIVE_AI":
                    is_interactive = True
                    raw_script = ""
                elif c_type == "SCRIPT" and not script_content:
                    is_interactive = False
                    raw_script = getattr(camp, "script_content", "") or ""

                if getattr(camp, "voice_model", None):
                    voice = camp.voice_model

                cc = db.query(CampaignContact).filter(CampaignContact.campaign_id == camp.id).first()
                if cc:
                    ct = db.query(Contact).filter(Contact.id == cc.contact_id).first()
                    if ct and ct.phone_number:
                        target_phone = ct.phone_number
        except Exception as ex:
            print(f"[Campaign DB Query Warning] {ex}")
        finally:
            db.close()

    caller = MicroSIPDirectCaller()
    _active_caller_instance = caller
    
    # Create & bind active RTP socket FIRST so the exact bound port is offered in the SIP INVITE SDP!
    rtp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    for p in [9098, 9099, 9100, 9102, 0]:
        try:
            rtp_sock.bind(("127.0.0.1", p))
            break
        except Exception:
            continue
    rtp_sock.settimeout(0.2)
    caller.rtp_port = rtp_sock.getsockname()[1]
    print(f"📡 [RTP MEDIA BRIDGE] Bound local RTP audio socket on port {caller.rtp_port}")

    await caller.trigger_microsip_ring()

    if not caller.is_answered:
        rtp_sock.close()
        return

    start_time = datetime.utcnow()
    call_id_db = str(uuid.uuid4())
    log_gateway_event(f"Call session started with call_id={call_id_db}")
    transcript_turns = []

    # Immediately insert active in_progress session into SQLite DB so Live Monitor sees it
    try:
        db_start = SessionLocal()
        org = db_start.query(Organization).first()
        org_id = org.id if org else call_id_db
        init_session = CallSession(
            id=call_id_db,
            organization_id=org_id,
            contact_id=None,
            provider="microsip_direct",
            direction="outbound",
            from_number="+918000000700",
            to_number=target_phone,
            status="in_progress",
            started_at=start_time,
            duration_s=0,
            transcript=transcript_turns
        )
        db_start.add(init_session)
        db_start.commit()
        db_start.close()
    except Exception as init_ex:
        print(f"   ⚠️ [DB Session Init Warning] {init_ex}")



    if is_interactive:
        print("\n🤖 [STARTING LIVE INTERACTIVE AI AGENT CALL - SEPARATED FROM SCRIPT RECITATIONS]")
        # 1. AI Agent Greeting (Short, Natural, Human Opening)
        greeting = "Hello! How can I help you today?"
        transcript_turns.append({"role": "assistant", "content": greeting})
        # ⚡ INITIAL GREETING: check_barge_in=False so mic click when clicking Answer NEVER aborts initial greeting!
        await speak_text_to_microsip(rtp_sock, caller.remote_rtp_port, greeting, voice=voice, check_barge_in=False)

        # 2. System Persona (Clean Conversational & Word Test Partner)
        llm_persona = system_prompt.strip() if (system_prompt and system_prompt.strip()) else (
            "You are Ananya, a warm, friendly, and highly intelligent human-like AI voice assistant at Superfone.\n"
            "STRICT RULES:\n"
            "1. Respond directly and accurately to whatever the user says in 1 short spoken sentence.\n"
            "2. If the user speaks a test word like hello, chalo, yellow, yalo, khalo, bhalo, or dabalo, acknowledge it warmly (e.g. 'Got it, chalo!', 'Heard yellow!').\n"
            "3. Speak naturally in English or Hinglish/Hindi based on what the user says."
        )

        # Interactive Multi-Turn Conversation Loop (Up to 10 turns)
        conversation_history = [
            {"role": "system", "content": llm_persona},
            {"role": "assistant", "content": greeting}
        ]

        for turn_idx in range(10):
            if not caller.is_answered:
                break

            rtp_sock.settimeout(0.2)

            incoming_pcm = bytearray()
            t_listen = time.time()
            user_spoken = False
            speech_frames = 0
            silence_start = None

            while time.time() - t_listen < 6.5:
                try:
                    pkt, _ = rtp_sock.recvfrom(2048)
                    if len(pkt) > 12:
                        ulaw_payload = pkt[12:]
                        pcm_data = audioop.ulaw2lin(ulaw_payload, 2)
                        incoming_pcm.extend(pcm_data)
                        caller.recording_pcm.extend(pcm_data)

                        rms = audioop.rms(pcm_data, 2)
                        if rms > 220:  # Verified speech frame
                            speech_frames += 1
                            if speech_frames >= 3:
                                user_spoken = True
                                silence_start = None
                        elif user_spoken:
                            if silence_start is None:
                                silence_start = time.time()
                            elif time.time() - silence_start >= 0.35:
                                print("   ⚡ [VAD] End of user speech detected (0.35s ultra-fast cutoff)!")
                                break
                except (socket.timeout, ConnectionResetError, OSError):
                    pass
                await asyncio.sleep(0.005)

            if not user_spoken or len(incoming_pcm) < 800:
                print("   👤 USER: [No speech / Silence - Re-listening...]")
                continue

            user_text = ""
            audio_sec = round(len(incoming_pcm) / 16000.0, 2)
            t_stt_start = time.time()

            # ⚡ DYNAMIC MICROPHONE GAIN NORMALIZATION (Boost soft speech to 0.85 peak headroom)
            raw_stt_bytes = bytes(incoming_pcm)
            samples_mic = np.frombuffer(raw_stt_bytes, dtype=np.int16).astype(np.float32)
            max_p = np.max(np.abs(samples_mic)) if len(samples_mic) > 0 else 0.0
            if 250.0 < max_p < 25000.0:
                gain = (32767.0 * 0.85) / max_p
                samples_boosted = np.clip(samples_mic * gain, -32768, 32767).astype(np.int16)
                stt_audio_bytes = samples_boosted.tobytes()
            else:
                stt_audio_bytes = raw_stt_bytes

            # ⚡ 1. PRIMARY ULTRA-FAST CLOUD STT: GROQ WHISPER-LARGE-V3-TURBO (~350ms LATENCY)
            if GROQ_API_KEY:
                try:
                    import io, wave
                    wav_io = io.BytesIO()
                    with wave.open(wav_io, "wb") as wf:
                        wf.setnchannels(1)
                        wf.setsampwidth(2)
                        wf.setframerate(8000)
                        wf.writeframes(stt_audio_bytes)
                    wav_mem = wav_io.getvalue()

                    files = {"file": ("speech.wav", wav_mem, "audio/wav")}
                    data = {
                        "model": "whisper-large-v3-turbo",
                        "language": "en"
                    }
                    headers = {"Authorization": f"Bearer {GROQ_API_KEY}"}

                    async with httpx.AsyncClient() as client:
                        groq_res = await client.post(
                            "https://api.groq.com/openai/v1/audio/transcriptions",
                            headers=headers,
                            files=files,
                            data=data,
                            timeout=3.5
                        )
                        stt_ms = round((time.time() - t_stt_start) * 1000, 1)
                        if groq_res.status_code == 200:
                            raw_txt = groq_res.json().get("text", "").strip()
                            if raw_txt.lower().rstrip('.!') in ["thank you", "thanks", "amen", "you"] and max_p < 3000:
                                print(f"   ⚠️ [WHISPER SILENCE HALLUCINATION DISCARDED]: '{raw_txt}' (Peak={max_p}) -> Re-listening...")
                                user_text = ""
                            else:
                                user_text = raw_txt
                                print(f"   ⚡ [GROQ WHISPER-TURBO STT] Transcribed {len(incoming_pcm)} bytes ({audio_sec}s audio) in {stt_ms}ms -> '{user_text}'")
                        else:
                            print(f"   ⚠️ [Groq STT HTTP {groq_res.status_code}]: {groq_res.text}")
                except Exception as groq_stt_ex:
                    print(f"   ⚠️ [Groq STT Exception: {groq_stt_ex}] -> Trying Deepgram fallback...")

            # ⚡ 2. SECONDARY CLOUD STT: DEEPGRAM NOVA-2 (Zero rate limits, ~250ms latency)
            if not user_text:
                try:
                    from path_c_hybrid_agent.config import DEEPGRAM_API_KEY
                    if DEEPGRAM_API_KEY:
                        import io, wave
                        wav_io = io.BytesIO()
                        with wave.open(wav_io, "wb") as wf:
                            wf.setnchannels(1)
                            wf.setsampwidth(2)
                            wf.setframerate(8000)
                            wf.writeframes(stt_audio_bytes)
                        wav_mem = wav_io.getvalue()

                        async with httpx.AsyncClient() as client:
                            dg_res = await client.post(
                                "https://api.deepgram.com/v1/listen?model=nova-2&smart_format=true",
                                headers={
                                    "Authorization": f"Token {DEEPGRAM_API_KEY}",
                                    "Content-Type": "audio/wav"
                                },
                                content=wav_mem,
                                timeout=3.5
                            )
                            stt_ms = round((time.time() - t_stt_start) * 1000, 1)
                            if dg_res.status_code == 200:
                                tx = dg_res.json()["results"]["channels"][0]["alternatives"][0]["transcript"].strip()
                                if tx:
                                    user_text = tx
                                    print(f"   ⚡ [DEEPGRAM NOVA-2 STT] Transcribed ({audio_sec}s audio) in {stt_ms}ms -> '{user_text}'")
                except Exception as dg_ex:
                    print(f"   ⚠️ [Deepgram STT Warning]: {dg_ex}")

            # ⚡ 3. IN-PROCESS FASTER-WHISPER LOCAL FALLBACK
            if not user_text:
                try:
                    from services.stt.worker import transcribe_audio, whisper_model, init_worker
                    if whisper_model is None:
                        init_worker()
                    res = transcribe_audio(stt_audio_bytes, time.time())
                    user_text = res.get("text", "").strip()
                    stt_ms = round((time.time() - t_stt_start) * 1000, 1)
                    print(f"   🧠 [IN-PROCESS FAST STT FALLBACK] Transcribed in {stt_ms}ms -> '{user_text}'")
                except Exception as stt_ex:
                    print(f"   ⚠️ [In-Process STT Notice: {stt_ex}]")

            if not user_text:
                print("   👤 USER: [No speech / Silence - Re-listening...]")
                continue

            # Save live microphone audio file for user verification
            artifact_dir = r"C:\Users\msanj\.gemini\antigravity\brain\8fd7d2de-313c-4386-802f-400cc03a7507"
            wav_name = f"live_mic_turn_{turn_idx+1}.wav"
            wav_path = os.path.join(artifact_dir, wav_name).replace("\\", "/")
            try:
                import wave
                with wave.open(wav_path, "wb") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(8000)
                    wf.writeframes(incoming_pcm)
                print(f"   🎙️ [LIVE MIC AUDIO SAVED]: file:///{wav_path} ({audio_sec}s)")
            except Exception as wav_ex:
                print(f"   ⚠️ [WAV Save Warning] {wav_ex}")

            print(f"👤 USER SPOKE: \"{user_text}\" ({audio_sec}s audio captured)")
            log_gateway_event(f"USER_UTTERANCE text='{user_text}' call_id='{call_id_db}'")
            user_turn_data = {
                "role": "user",
                "content": user_text,
                "live_mic": True,
                "audio_dur_s": audio_sec,
                "wav_file": wav_name
            }
            transcript_turns.append(user_turn_data)
            conversation_history.append({"role": "user", "content": user_text})


            # Real-time DB sync after user utterance
            try:
                db_live = SessionLocal()
                sess_rec = db_live.query(CallSession).filter(CallSession.id == call_id_db).first()
                if sess_rec:
                    sess_rec.transcript = list(transcript_turns)
                    db_live.commit()
                db_live.close()
            except Exception:
                pass

            # Generate dynamic response via Groq Cloud LLM (Model: qwen/qwen3.8-27b, temp=0.3)
            ai_reply = ""
            try:
                from path_c_hybrid_agent.config import GROQ_API_KEY as groq_key
            except Exception:
                groq_key = os.environ.get("GROQ_API_KEY", "")

            if groq_key:
                try:
                    async with httpx.AsyncClient() as client:
                        g_resp = await client.post(
                            "https://api.groq.com/openai/v1/chat/completions",
                            headers={"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"},
                            json={
                                "model": "qwen/qwen3.8-27b",
                                "messages": conversation_history,
                                "max_tokens": 35,
                                "temperature": 0.3
                            },
                            timeout=3.5
                        )
                        if g_resp.status_code == 200:
                            choices = g_resp.json().get("choices", [])
                            if choices and "message" in choices[0]:
                                ai_reply = choices[0]["message"]["content"].strip()
                                print(f"⚡ [GROQ CLOUD LLM DYNAMIC REPLY]: \"{ai_reply}\"")
                except Exception as g_ex:
                    print(f"   ⚠️ [Groq Cloud Warning] {g_ex}")

            if not ai_reply:
                # Local LLM fallback
                try:
                    async with httpx.AsyncClient() as client:
                        llm_resp = await client.post("http://127.0.0.1:9093/v1/chat/completions", json={
                            "messages": conversation_history
                        }, timeout=3.0)
                        if llm_resp.status_code == 200:
                            choices = llm_resp.json().get("choices", [])
                            if choices and "message" in choices[0]:
                                ai_reply = choices[0]["message"]["content"].strip()
                                print(f"🤖 [LOCAL LLM FALLBACK REPLY]: \"{ai_reply}\"")
                except Exception as ex:
                    print(f"   ⚠️ [Local LLM Warning] {ex}")

            if not ai_reply:
                ai_reply = "Ji haan, main aapki baat sun raha hoon. Kripya batayein main aapki kya madad kar sakta hoon?"
                print(f"💬 [CONVERSATIONAL FALLBACK REPLY]: \"{ai_reply}\"")

            if ai_reply:
                transcript_turns.append({"role": "assistant", "content": ai_reply})
                conversation_history.append({"role": "assistant", "content": ai_reply})
                log_gateway_event(f"AI_RESPONSE text='{ai_reply}' call_id='{call_id_db}'")


                # Real-time DB sync after assistant utterance
                try:
                    db_live = SessionLocal()
                    sess_rec = db_live.query(CallSession).filter(CallSession.id == call_id_db).first()
                    if sess_rec:
                        sess_rec.transcript = list(transcript_turns)
                        db_live.commit()
                    db_live.close()
                except Exception:
                    pass

                await speak_text_to_microsip(rtp_sock, caller.remote_rtp_port, ai_reply, voice=voice, check_barge_in=False)
            else:
                print("   🤖 AI AGENT: [No reply generated]")

    else:
        # Pure Script Recitation Mode
        print(f"\n📜 [AI AGENT RECITING SCRIPT TO MICROSIP]:\n\"{raw_script}\"")
        if raw_script:
            raw_lines = [l.strip() for l in raw_script.split('\n') if l.strip()]
            for l in raw_lines:
                transcript_turns.append({"role": "assistant", "content": l})
            await speak_text_to_microsip(rtp_sock, caller.remote_rtp_port, raw_script, voice=voice)
        else:
            transcript_turns = [{"role": "assistant", "content": "[No speech script provided]"}]

    # Save call record & AI interaction to CRM database
    end_time = datetime.utcnow()
    duration_s = round((end_time - start_time).total_seconds(), 1)
    
    # Save full call audio recording to recordings directory
    rec_dir = r"c:\daily_works\superfone_call\recordings"
    os.makedirs(rec_dir, exist_ok=True)
    full_rec_filename = f"{call_id_db}.wav"
    full_rec_path = os.path.join(rec_dir, full_rec_filename)
    recording_url_val = f"/recordings/{full_rec_filename}"

    try:
        if caller.recording_pcm and len(caller.recording_pcm) > 0:
            import wave
            with wave.open(full_rec_path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(8000)
                wf.writeframes(bytes(caller.recording_pcm))
            print(f"🎙️ [FULL CALL RECORDING SAVED]: {full_rec_path} ({len(caller.recording_pcm)} bytes)")
    except Exception as rec_ex:
        print(f"[Full Call Recording Save Warning] {rec_ex}")

    db = SessionLocal()
    try:
        session_rec = db.query(CallSession).filter(CallSession.id == call_id_db).first()
        if not session_rec:
            org = db.query(Organization).first()
            org_id = org.id if org else call_id_db
            session_rec = CallSession(
                id=call_id_db,
                organization_id=org_id,
                contact_id=None,
                provider="microsip_direct",
                direction="outbound",
                from_number="+918000000700",
                to_number=target_phone,
                started_at=start_time
            )
            db.add(session_rec)

        session_rec.status = "completed"
        session_rec.ended_at = end_time
        session_rec.duration_s = duration_s
        session_rec.recording_url = recording_url_val
        session_rec.transcript = list(transcript_turns)


        intent_tag = "INTERACTIVE_AI_CONVERSATION" if is_interactive else "SCRIPT_RECITATION"
        summary_txt = f"Interactive AI call ({len(transcript_turns)} turns, {duration_s}s)." if is_interactive else f"Outbound script call ({duration_s}s)."

        interaction = CallInteraction(
            call_id=call_id_db,
            intent_detected=intent_tag,
            confidence=0.98,
            ai_summary=summary_txt
        )
        db.add(interaction)
        db.commit()
        log_gateway_event(f"Call session finished with call_id={call_id_db}")
        print(f"\n💾 [CALL SESSION & TRANSCRIPT RECORDED IN CRM DB! Call ID: {call_id_db}]")

    except Exception as ex:
        print(f"[Call DB Save Warning] {ex}")
    finally:
        db.close()

    # 3. Gracefully terminate SIP dialog so MicroSIP resets back to IDLE state for future calls
    await caller.send_bye()
    rtp_sock.close()
    try:
        caller.sip_sock.close()
    except Exception:
        pass
    print("\n=" * 70)
    print("  MICROSIP CALL SESSION COMPLETED CLEANLY!")
    print("=" * 70)

if __name__ == "__main__":
    print("=" * 70)
    print("  SUPERFONE MICROSIP DIRECT TELEPHONY ENGINE")
    print("=" * 70)
    print("✅ Engine loaded and ready for API call triggers.")
    print("   Calls will ONLY be originated when triggered via Manual Dial or Campaign!")
    print("=" * 70)
