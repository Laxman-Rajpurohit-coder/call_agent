import time
import socket
import asyncio
from typing import List, Dict, Any
from services.dashboard.app.config import settings

SERVICES_TO_MONITOR = [
    {"name": "Call Gateway", "port": 9092, "url": settings.CALL_GATEWAY_URL},
    {"name": "LLM Engine", "port": 9093, "url": settings.LLM_SERVER_URL},
    {"name": "STT Worker", "port": 9094, "url": settings.STT_WORKER_URL},
    {"name": "TTS Worker", "port": 9095, "url": settings.TTS_WORKER_URL},
    {"name": "Audio Studio", "port": 9096, "url": settings.AUDIO_STUDIO_URL},
]

async def _check_single_service(svc: Dict[str, Any]) -> Dict[str, Any]:
    port = svc["port"]
    t0 = time.perf_counter()
    status = "offline"
    latency_ms = None

    try:
        # Fast async socket connect
        fut = asyncio.open_connection("127.0.0.1", port)
        reader, writer = await asyncio.wait_for(fut, timeout=0.25)
        writer.close()
        await writer.wait_closed()
        status = "healthy"
        latency_ms = round((time.perf_counter() - t0) * 1000, 2)
    except Exception:
        status = "offline"
        latency_ms = None

    return {
        "name": svc["name"],
        "port": svc["port"],
        "url": svc["url"],
        "status": status,
        "latency_ms": latency_ms
    }

async def check_all_services() -> List[Dict[str, Any]]:
    tasks = [_check_single_service(svc) for svc in SERVICES_TO_MONITOR]
    return await asyncio.gather(*tasks)
