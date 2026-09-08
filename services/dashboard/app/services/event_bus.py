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

manager = ConnectionManager()

def parse_log_line(line: str) -> dict:
    ts_match = re.match(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3})", line)
    timestamp = ts_match.group(1) if ts_match else ""

    event_type = "LOG"
    call_id = ""
    payload = {}

    if "Call session started with call_id=" in line:
        event_type = "CALL_STARTED"
        cid_match = re.search(r"call_id=([a-f0-9\-]+)", line)
        call_id = cid_match.group(1) if cid_match else ""
    elif "USER_UTTERANCE" in line or "USER SPOKE:" in line:
        event_type = "USER_UTTERANCE"
        m = re.search(r"text='([^']*)'", line)
        if not m:
            m = re.search(r'USER SPOKE:\s*"([^"]*)"', line)
        payload["text"] = m.group(1) if m else line
    elif "AI_RESPONSE" in line or "LLM DYNAMIC REPLY" in line or "LLM FALLBACK REPLY" in line:
        event_type = "AI_RESPONSE"
        m = re.search(r"text='([^']*)'", line)
        if not m:
            m = re.search(r'REPLY\]:\s*"([^"]*)"', line)
        payload["text"] = m.group(1) if m else line
    elif "BARGE_IN_TRIGGERED" in line:
        event_type = "BARGE_IN_TRIGGERED"
        m = re.search(r"reason='([^']*)'", line)
        payload["reason"] = m.group(1) if m else "caller spoke"
    elif "DTMF 0 detected" in line:
        event_type = "DTMF_HANDOFF"
        payload["dtmf"] = "0"
    elif "Call session finished" in line or "Call disconnected" in line:
        event_type = "CALL_ENDED"


    return {
        "timestamp": timestamp,
        "event_type": event_type,
        "call_id": call_id,
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
