import os
import asyncio
import json
import re
from typing import List
from fastapi import WebSocket
from services.dashboard.app.config import settings

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                pass

import uuid

from services.dashboard.app.services.call_registry import call_registry

manager = ConnectionManager()
_global_event_seq = 0

async def broadcast_call_event(event_type: str, call_id: str, payload: dict = None):
    """Authoritative direct WebSocket event broadcaster for telephony and STT/AI engine."""
    global _global_event_seq
    _global_event_seq += 1
    seq = call_registry.get_next_sequence(call_id) if call_id else _global_event_seq
    envelope = {
        "event_id": f"evt_{uuid.uuid4().hex[:12]}",
        "event": event_type,
        "event_type": event_type,  # Backwards compatibility
        "call_id": call_id or "",
        "timestamp": datetime.utcnow().isoformat(),
        "sequence": seq,
        "payload": payload or {}
    }
    await manager.broadcast(envelope)
    return envelope

from datetime import datetime

def parse_log_line(line: str) -> dict:
    global _global_event_seq
    _global_event_seq += 1
    ts_match = re.match(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3})", line)
    timestamp = ts_match.group(1) if ts_match else datetime.utcnow().isoformat()

    event_type = "LOG"
    call_id = ""
    payload = {}

    if "Call session started with call_id=" in line:
        event_type = "CALL_CONNECTED"
        cid_match = re.search(r"call_id=([a-f0-9\-]+)", line)
        call_id = cid_match.group(1) if cid_match else ""
        payload = {"status": "CONNECTED", "handler": {"type": "AI", "name": "Superfone AI"}}
    elif "USER_UTTERANCE" in line or "USER SPOKE:" in line:
        event_type = "TRANSCRIPT_FINAL"
        cid_match = re.search(r"call_id='([^']*)'", line)
        if cid_match:
            call_id = cid_match.group(1)
        m = re.search(r"text='(.*)'\s*$", line)  # greedy to the last quote so apostrophes (I'm) survive
        if not m:
            m = re.search(r'USER SPOKE:\s*"([^"]*)"', line)
        payload["speaker"] = "USER"
        payload["text"] = m.group(1) if m else line
    elif "AI_RESPONSE" in line or "LLM DYNAMIC REPLY" in line or "LLM FALLBACK REPLY" in line:
        event_type = "TRANSCRIPT_FINAL"
        cid_match = re.search(r"call_id='([^']*)'", line)
        if cid_match:
            call_id = cid_match.group(1)
        m = re.search(r"text='(.*)'\s*$", line)  # greedy to the last quote so apostrophes (I'm) survive
        if not m:
            m = re.search(r'REPLY\]:\s*"([^"]*)"', line)
        payload["speaker"] = "AI"
        payload["text"] = m.group(1) if m else line
    elif "BARGE_IN_TRIGGERED" in line:
        event_type = "BARGE_IN_TRIGGERED"
        m = re.search(r"reason='([^']*)'", line)
        payload["reason"] = m.group(1) if m else "caller spoke"
    elif "DTMF 0 detected" in line:
        event_type = "DTMF_HANDOFF"
        payload["dtmf"] = "0"
    elif "Call session finished" in line or "Call disconnected" in line or "CALL_ENDED" in line:
        event_type = "CALL_ENDED"
        cid_match = re.search(r"call_id='?([a-f0-9\-]+)'?", line)
        call_id = cid_match.group(1) if cid_match else ""
        payload = {"reason": "CALL_ENDED"}

    seq = call_registry.get_next_sequence(call_id) if call_id else _global_event_seq
    return {
        "event_id": f"evt_{uuid.uuid4().hex[:12]}",
        "event": event_type,
        "event_type": event_type,  # Backwards compatibility
        "call_id": call_id,
        "timestamp": timestamp,
        "sequence": seq,
        "raw": line,
        "payload": payload
    }

async def log_tailer_task():
    log_file = settings.CALL_GATEWAY_LOG
    if not os.path.exists(log_file):
        with open(log_file, "w", encoding="utf-8") as f:
            f.write("")

    with open(log_file, "r", encoding="utf-8", errors="replace") as f:
        f.seek(0, os.SEEK_END)
        while True:
            line = f.readline()
            if not line:
                await asyncio.sleep(0.1)
                continue
            parsed = parse_log_line(line.strip())
            await manager.broadcast(parsed)
