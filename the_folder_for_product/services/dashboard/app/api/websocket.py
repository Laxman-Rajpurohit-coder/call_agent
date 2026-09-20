from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from services.dashboard.app.services.event_bus import manager

router = APIRouter(prefix="/ws", tags=["WebSocket"])

@router.websocket("/live")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
