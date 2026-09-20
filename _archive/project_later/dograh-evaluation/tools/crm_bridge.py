import os
import json
import sqlite3
from typing import Optional, Dict, Any, List
from aiohttp import web

DB_PATH = os.environ.get("CRM_DB_PATH", os.path.join(os.path.dirname(__file__), "crm.db"))


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS customers (
            customer_id TEXT PRIMARY KEY,
            name TEXT,
            phone_number TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS customer_tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id TEXT NOT NULL,
            tag TEXT NOT NULL,
            reason TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS call_notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            call_id TEXT NOT NULL,
            customer_id TEXT,
            summary TEXT NOT NULL,
            action_items TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS scheduled_callbacks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id TEXT NOT NULL,
            phone_number TEXT NOT NULL,
            scheduled_time TEXT NOT NULL,
            status TEXT DEFAULT 'PENDING',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)
        cursor.execute("""
        INSERT OR IGNORE INTO customers (customer_id, name, phone_number)
        VALUES ('cust_001', 'Test Caller', '+919876543210');
        """)
        conn.commit()


init_db()

# ── Tool Core Logic ──────────────────────────────────────────────────────────

def exec_tag_customer(customer_id: str, tag: str, reason: str) -> Dict[str, Any]:
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO customer_tags (customer_id, tag, reason) VALUES (?, ?, ?)",
            (customer_id, tag, reason)
        )
        tag_id = cursor.lastrowid
        conn.commit()
    return {
        "status": "SUCCESS",
        "tag_id": tag_id,
        "customer_id": customer_id,
        "tag": tag,
        "reason": reason
    }

def exec_save_call_note(call_id: str, summary: str, action_items: Optional[str] = None, customer_id: Optional[str] = "cust_001") -> Dict[str, Any]:
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO call_notes (call_id, customer_id, summary, action_items) VALUES (?, ?, ?, ?)",
            (call_id, customer_id, summary, action_items)
        )
        note_id = cursor.lastrowid
        conn.commit()
    return {
        "status": "SUCCESS",
        "note_id": note_id,
        "call_id": call_id,
        "summary": summary,
        "action_items": action_items
    }

def exec_schedule_callback(customer_id: str, phone_number: str, scheduled_time: str) -> Dict[str, Any]:
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO scheduled_callbacks (customer_id, phone_number, scheduled_time) VALUES (?, ?, ?)",
            (customer_id, phone_number, scheduled_time)
        )
        callback_id = cursor.lastrowid
        conn.commit()
    return {
        "status": "SUCCESS",
        "callback_id": callback_id,
        "customer_id": customer_id,
        "phone_number": phone_number,
        "scheduled_time": scheduled_time
    }

def get_records(table_name: str) -> List[Dict[str, Any]]:
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(f"SELECT * FROM {table_name} ORDER BY id DESC" if table_name != "customers" else f"SELECT * FROM {table_name}")
        return [dict(row) for row in cursor.fetchall()]

# ── HTTP Handlers (aiohttp) ──────────────────────────────────────────────────

async def handle_tag_customer(request: web.Request) -> web.Response:
    data = await request.json()
    res = exec_tag_customer(data.get("customer_id", "cust_001"), data.get("tag", "general"), data.get("reason", ""))
    return web.json_response(res)

async def handle_save_call_note(request: web.Request) -> web.Response:
    data = await request.json()
    res = exec_save_call_note(data.get("call_id", "unknown"), data.get("summary", ""), data.get("action_items"), data.get("customer_id", "cust_001"))
    return web.json_response(res)

async def handle_schedule_callback(request: web.Request) -> web.Response:
    data = await request.json()
    res = exec_schedule_callback(data.get("customer_id", "cust_001"), data.get("phone_number", ""), data.get("scheduled_time", ""))
    return web.json_response(res)

async def handle_verify(request: web.Request) -> web.Response:
    table = request.match_info.get("table_name", "")
    if table not in ["customers", "customer_tags", "call_notes", "scheduled_callbacks"]:
        return web.json_response({"error": "Invalid table"}, status=400)
    records = get_records(table)
    return web.json_response(records)

async def handle_health(request: web.Request) -> web.Response:
    return web.json_response({
        "status": "healthy",
        "service": "superfone-crm-bridge",
        "database": DB_PATH,
        "tools": ["tag_customer", "save_call_note", "schedule_callback"]
    })

def create_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/health", handle_health)
    app.router.add_post("/tools/tag_customer", handle_tag_customer)
    app.router.add_post("/tools/save_call_note", handle_save_call_note)
    app.router.add_post("/tools/schedule_callback", handle_schedule_callback)
    app.router.add_get("/tools/verify/{table_name}", handle_verify)
    return app

if __name__ == "__main__":
    web.run_app(create_app(), host="127.0.0.1", port=9098)
