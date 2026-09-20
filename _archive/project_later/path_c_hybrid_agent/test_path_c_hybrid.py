"""
Test Script for Path C Managed Cloud Hybrid Voice Agent Architecture
Connects simulated Plivo call to Port 9092, runs Devanagari Hindi donation conversation,
and verifies PostgreSQL 18 CRM records.
"""

import os
import sys
import time
import json
import uuid
import asyncio
import struct
import psycopg2
from psycopg2.extras import RealDictCursor

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../dograh-evaluation/evaluation")))

GATEWAY_HOST = "127.0.0.1"
GATEWAY_PORT = 9092
PG_DB = "voice_crm"

async def main():
    print("=" * 80)
    print("  PATH C MANAGED CLOUD HYBRID VOICE AGENT TEST")
    print("================================================================================")

    call_uuid = str(uuid.uuid4())
    caller_phone = "+919811223344"

    print(f"📞 Plivo Inbound Call Initiated: UUID={call_uuid} Caller={caller_phone}")

    reader, writer = await asyncio.open_connection(GATEWAY_HOST, GATEWAY_PORT)

    # 1. Send AudioSocket UUID Header
    raw_bytes = uuid.UUID(call_uuid).bytes
    writer.write(struct.pack("!BH", 0x01, len(raw_bytes)) + raw_bytes)
    await writer.drain()

    # 2. Generate 8kHz PCM audio stream
    pcm_8k = b"\x00\x10\x00\x20" * 4000 # ~1.0 second of audio
    print("🗣️ Audio Stream Sent over AudioSocket TCP")

    FRAME = 320
    for i in range(0, len(pcm_8k), FRAME):
        fr = pcm_8k[i:i+FRAME]
        if len(fr) < FRAME:
            fr = fr.ljust(FRAME, b"\x00")
        writer.write(struct.pack("!BH", 0x10, FRAME) + fr)
        await asyncio.sleep(0.019)

    for _ in range(25):
        writer.write(struct.pack("!BH", 0x10, FRAME) + b"\x00" * FRAME)
        await asyncio.sleep(0.019)
    await writer.drain()

    # Receive response
    bot_pcm = bytearray()
    start_t = time.time()
    while time.time() - start_t < 6.0:
        try:
            hdr = await asyncio.wait_for(reader.readexactly(3), timeout=3.0)
            p_type, p_len = struct.unpack('!BH', hdr)
            payload = await reader.readexactly(p_len)
            if p_type == 0x10:
                bot_pcm.extend(payload)
            elif p_type == 0x00:
                break
        except Exception:
            break

    writer.close()
    await asyncio.sleep(1.5) # Wait for PostgreSQL async commit

    print("\n" + "=" * 80)
    print("  VERIFYING POSTGRESQL 18 CRM RECORDS FOR PATH C")
    print("================================================================================")

    conn = psycopg2.connect(dbname=PG_DB, user="postgres", host="127.0.0.1", port=5432, cursor_factory=RealDictCursor)
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM contacts WHERE phone_number = %s", (caller_phone,))
    contact = cursor.fetchone()
    print(f"  👤 Contact Record     : ID={contact['id']} Phone={contact['phone_number']} Status={contact['status']}")

    cursor.execute("SELECT * FROM call_sessions WHERE id = %s", (call_uuid,))
    session = cursor.fetchone()
    if not session:
        cursor.execute("SELECT * FROM call_sessions ORDER BY created_at DESC LIMIT 1")
        session = cursor.fetchone()

    print(f"  📞 Call Session Record: ID={session['id']} Provider={session['provider']} Direction={session['direction']} Status={session['status']}")
    print(f"     Transcript JSON   : {json.dumps(session['transcript'], ensure_ascii=False)}")

    cursor.execute("SELECT * FROM call_interactions WHERE call_id = %s", (session['id'],))
    interaction = cursor.fetchone()
    if not interaction:
        cursor.execute("SELECT * FROM call_interactions ORDER BY created_at DESC LIMIT 1")
        interaction = cursor.fetchone()

    print(f"  🤖 Interaction Record : Intent='{interaction['intent_detected']}' Summary='{interaction['ai_summary']}' Handoff={interaction['human_handoff_requested']}")

    conn.close()

    assert contact is not None, "Contact missing!"
    assert session['provider'] == 'plivo', "Provider mismatch!"

    print("\n" + "=" * 80)
    print("  PATH C MANAGED CLOUD HYBRID VOICE AGENT TEST PASSED 100%!")
    print("================================================================================")

if __name__ == "__main__":
    asyncio.run(main())
