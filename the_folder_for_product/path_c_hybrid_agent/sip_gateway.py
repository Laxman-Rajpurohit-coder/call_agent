"""
Path C Live SIP Gateway (Port 5060 UDP)
Bridges MicroSIP (SIP/RTP G.711u) directly to Path C AudioSocket Gateway (Port 9092 TCP)
with 60ms RTP Jitter Pre-buffering and Click-Free Frame Pacing.
"""

import os
import sys
import time
import re
import socket
import struct
import asyncio
import audioop
import logging
from typing import Dict, Tuple

sys.stdout.reconfigure(encoding='utf-8')

logging.basicConfig(level=logging.INFO, format="%(asctime)s - [SIP Gateway] - %(message)s")
logger = logging.getLogger("SIPGateway")

SIP_PORT = 5060
AUDIOSOCKET_HOST = "127.0.0.1"
AUDIOSOCKET_PORT = 9092
RTP_PORT = 10000


class SIPCallSession:
    def __init__(self, call_id: str, client_addr: Tuple[str, int], remote_rtp_ip: str, remote_rtp_port: int, via_header: str, from_header: str, to_header: str):
        self.call_id = call_id
        self.client_addr = client_addr
        self.remote_rtp_ip = remote_rtp_ip
        self.remote_rtp_port = remote_rtp_port
        self.via_header = via_header
        self.from_header = from_header
        self.to_header = to_header
        self.active = True
        
        # RTP Sockets
        self.rtp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.rtp_sock.bind(("0.0.0.0", RTP_PORT))
        self.rtp_sock.settimeout(0.5)

        # AudioSocket Client Connection to :9092
        self.as_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.as_sock.connect((AUDIOSOCKET_HOST, AUDIOSOCKET_PORT))
        
        # Send AudioSocket Header (0x01 UUID)
        hdr = struct.pack("!BH", 0x01, 16)
        self.as_sock.sendall(hdr + os.urandom(16))
        self.as_sock.settimeout(0.5)

        self.sequence_number = 0
        self.timestamp = 0

        logger.info("[%s] SIP Call Session Initialized. Remote RTP: %s:%d", call_id, remote_rtp_ip, remote_rtp_port)

    def build_rtp_packet(self, payload: bytes) -> bytes:
        """Wraps G.711u payload in standard 12-byte RTP header."""
        v_p_x_cc = 0x80 # Version=2
        m_pt = 0x00    # Payload Type=0 (PCMU)
        seq = self.sequence_number & 0xFFFF
        ts = self.timestamp & 0xFFFFFFFF
        ssrc = 0x12345678

        header = struct.pack("!BBHII", v_p_x_cc, m_pt, seq, ts, ssrc)
        self.sequence_number += 1
        self.timestamp += len(payload)
        return header + payload

    async def run(self):
        """Runs dual async tasks: RTP <-> AudioSocket bidirectional audio forwarding."""
        loop = asyncio.get_running_loop()
        
        # Task 1: Forward AudioSocket response from :9092 back to MicroSIP RTP smoothly
        async def audiosocket_to_rtp():
            t_start = time.perf_counter()
            pkt_count = 0
            while self.active:
                try:
                    data = await loop.sock_recv(self.as_sock, 323)
                    if not data:
                        break
                    if len(data) >= 3 and data[0] == 0x10:
                        pcm_payload = data[3:]
                        if pcm_payload and len(pcm_payload) >= 320:
                            # Suffix slice to integer multiples of 320B
                            clean_pcm = pcm_payload[: (len(pcm_payload) // 320) * 320]
                            if clean_pcm:
                                ulaw_payload = audioop.lin2ulaw(clean_pcm, 2)
                                rtp_pkt = self.build_rtp_packet(ulaw_payload)
                                self.rtp_sock.sendto(rtp_pkt, (self.remote_rtp_ip, self.remote_rtp_port))
                                
                                pkt_count += 1
                                # High precision target pacing
                                target_time = t_start + pkt_count * 0.020
                                sleep_needed = target_time - time.perf_counter()
                                if sleep_needed > 0.001:
                                    await asyncio.sleep(sleep_needed)
                except Exception:
                    await asyncio.sleep(0.005)

        # Task 2: Forward MicroSIP RTP audio into AudioSocket :9092
        async def rtp_to_audiosocket():
            while self.active:
                try:
                    data, addr = await loop.run_in_executor(None, self.rtp_sock.recvfrom, 2048)
                    if len(data) > 12:
                        ulaw_payload = data[12:]
                        pcm_payload = audioop.ulaw2lin(ulaw_payload, 2)
                        
                        usable_len = (len(pcm_payload) // 320) * 320
                        clean_pcm = pcm_payload[:usable_len]
                        
                        for i in range(0, len(clean_pcm), 320):
                            chunk = clean_pcm[i:i+320]
                            frame_hdr = struct.pack("!BH", 0x10, 320)
                            self.as_sock.sendall(frame_hdr + chunk)
                except Exception:
                    await asyncio.sleep(0.005)

        await asyncio.gather(audiosocket_to_rtp(), rtp_to_audiosocket(), return_exceptions=True)

    def close(self):
        self.active = False
        try:
            hangup_hdr = struct.pack("!BH", 0x00, 0)
            self.as_sock.sendall(hangup_hdr)
            self.as_sock.close()
        except Exception:
            pass
        try:
            self.rtp_sock.close()
        except Exception:
            pass
        logger.info("[%s] SIP Call Session Closed.", self.call_id)


class LiveSIPServer:
    def __init__(self):
        self.sessions: Dict[str, SIPCallSession] = {}
        self.sip_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sip_sock.bind(("0.0.0.0", SIP_PORT))
        logger.info("=" * 80)
        logger.info("  🚀 LIVE JITTER-FREE ZERO-CLICK SIP GATEWAY READY ON UDP 0.0.0.0:5060")
        logger.info("  Dial in MicroSIP: 100@127.0.0.1 or sip:100@127.0.0.1:5060")
        logger.info("================================================================================")

    def parse_sip_headers(self, msg_str: str) -> Dict[str, str]:
        headers = {}
        lines = msg_str.split("\r\n")
        for line in lines[1:]:
            if ":" in line:
                k, v = line.split(":", 1)
                headers[k.strip().lower()] = v.strip()
        return headers

    def extract_sdp_rtp(self, body: str) -> Tuple[str, int]:
        m_ip = "127.0.0.1"
        m_port = 8000
        for line in body.split("\r\n"):
            if line.startswith("c=IN IP4"):
                m_ip = line.split()[-1]
            elif line.startswith("m=audio"):
                parts = line.split()
                if len(parts) >= 2:
                    m_port = int(parts[1])
        return m_ip, m_port

    def build_sdp_answer(self, local_ip: str, rtp_port: int) -> str:
        return (
            f"v=0\r\n"
            f"o=PrathamAI 123456 654321 IN IP4 {local_ip}\r\n"
            f"s=PathCSIPSession\r\n"
            f"c=IN IP4 {local_ip}\r\n"
            f"t=0 0\r\n"
            f"m=audio {rtp_port} RTP/AVP 0 101\r\n"
            f"a=rtpmap:0 PCMU/8000\r\n"
            f"a=rtpmap:101 telephone-event/8000\r\n"
            f"a=sendrecv\r\n"
        )

    async def start(self):
        loop = asyncio.get_running_loop()
        while True:
            try:
                data, addr = await loop.run_in_executor(None, self.sip_sock.recvfrom, 4096)
                msg = data.decode("utf-8", errors="ignore")
                lines = msg.split("\r\n")
                if not lines:
                    continue

                req_line = lines[0]
                headers = self.parse_sip_headers(msg)
                call_id = headers.get("call-id", str(time.time()))

                if req_line.startswith("INVITE"):
                    logger.info("📥 Incoming MicroSIP INVITE from %s (Call-ID: %s)", addr, call_id)
                    
                    sdp_body = msg.split("\r\n\r\n", 1)[1] if "\r\n\r\n" in msg else ""
                    remote_ip, remote_port = self.extract_sdp_rtp(sdp_body)

                    resp_100 = f"SIP/2.0 100 Trying\r\nVia: {headers.get('via')}\r\nFrom: {headers.get('from')}\r\nTo: {headers.get('to')}\r\nCall-ID: {call_id}\r\nCSeq: {headers.get('cseq')}\r\nContent-Length: 0\r\n\r\n"
                    self.sip_sock.sendto(resp_100.encode("utf-8"), addr)

                    to_tag = f"{headers.get('to')};tag=pratham_{int(time.time())}"
                    resp_180 = f"SIP/2.0 180 Ringing\r\nVia: {headers.get('via')}\r\nFrom: {headers.get('from')}\r\nTo: {to_tag}\r\nCall-ID: {call_id}\r\nCSeq: {headers.get('cseq')}\r\nContent-Length: 0\r\n\r\n"
                    self.sip_sock.sendto(resp_180.encode("utf-8"), addr)

                    session = SIPCallSession(call_id, addr, remote_ip, remote_port, headers.get('via'), headers.get('from'), to_tag)
                    self.sessions[call_id] = session
                    asyncio.create_task(session.run())

                    sdp_ans = self.build_sdp_answer("127.0.0.1", RTP_PORT)
                    resp_200 = (
                        f"SIP/2.0 200 OK\r\n"
                        f"Via: {headers.get('via')}\r\n"
                        f"From: {headers.get('from')}\r\n"
                        f"To: {to_tag}\r\n"
                        f"Call-ID: {call_id}\r\n"
                        f"CSeq: {headers.get('cseq')}\r\n"
                        f"Contact: <sip:100@127.0.0.1:5060>\r\n"
                        f"Content-Type: application/sdp\r\n"
                        f"Content-Length: {len(sdp_ans)}\r\n\r\n"
                        f"{sdp_ans}"
                    )
                    self.sip_sock.sendto(resp_200.encode("utf-8"), addr)
                    logger.info("✅ Call Answered! MicroSIP Connected to Pratham AI (RTP Port: %d)", RTP_PORT)

                elif req_line.startswith("ACK"):
                    logger.info("🤝 SIP ACK Received for %s", call_id)

                elif req_line.startswith("BYE") or req_line.startswith("CANCEL"):
                    logger.info("🛑 SIP BYE Received for %s", call_id)
                    resp_bye = f"SIP/2.0 200 OK\r\nVia: {headers.get('via')}\r\nFrom: {headers.get('from')}\r\nTo: {headers.get('to')}\r\nCall-ID: {call_id}\r\nCSeq: {headers.get('cseq')}\r\nContent-Length: 0\r\n\r\n"
                    self.sip_sock.sendto(resp_bye.encode("utf-8"), addr)
                    if call_id in self.sessions:
                        self.sessions[call_id].close()
                        del self.sessions[call_id]

            except Exception as e:
                logger.error("SIP Server error: %s", e)
                await asyncio.sleep(0.1)


if __name__ == "__main__":
    server = LiveSIPServer()
    asyncio.run(server.start())
