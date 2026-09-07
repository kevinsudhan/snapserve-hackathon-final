"""WS /ws/events — server pushes Event JSON; clients may send {"type":"ping"}."""

from __future__ import annotations

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.events import broadcaster, make_event

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ws"])


@router.websocket("/ws/events")
async def events(websocket: WebSocket) -> None:
    await broadcaster.connect(websocket)
    try:
        await websocket.send_json(
            make_event("poller.status", {"connected": True, "recent": len(broadcaster.recent)})
        )
        while True:
            message = await websocket.receive_json()
            if isinstance(message, dict) and message.get("type") == "ping":
                await websocket.send_json(make_event("pong", {}))
    except WebSocketDisconnect:
        pass
    except Exception as exc:  # pragma: no cover - client sent junk
        logger.debug("ws closed: %s", exc.__class__.__name__)
    finally:
        await broadcaster.disconnect(websocket)
