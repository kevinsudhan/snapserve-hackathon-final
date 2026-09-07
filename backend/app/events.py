"""WebSocket event bus.

``emit(type, payload)`` is awaited from the async pipeline; ``emit_threadsafe``
covers the rare sync caller.  Every event is also kept in a small ring buffer so
tests (and a late-joining dashboard) can inspect what happened.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections import deque
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import WebSocket

logger = logging.getLogger(__name__)

RECENT_LIMIT = 200


class EventBroadcaster:
    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._lock = asyncio.Lock()
        self.recent: deque[dict[str, Any]] = deque(maxlen=RECENT_LIMIT)
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    # -- lifecycle ------------------------------------------------------
    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._clients.add(websocket)
        logger.info("ws client connected (%d total)", len(self._clients))

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._clients.discard(websocket)
        logger.info("ws client disconnected (%d left)", len(self._clients))

    @property
    def client_count(self) -> int:
        return len(self._clients)

    # -- emitting -------------------------------------------------------
    async def broadcast(self, event: dict[str, Any]) -> None:
        self.recent.append(event)
        if not self._clients:
            return
        async with self._lock:
            targets = list(self._clients)
        dead: list[WebSocket] = []
        for client in targets:
            try:
                await client.send_json(event)
            except Exception:
                dead.append(client)
        if dead:
            async with self._lock:
                for client in dead:
                    self._clients.discard(client)

    def clear(self) -> None:
        self.recent.clear()


broadcaster = EventBroadcaster()


def make_event(event_type: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "type": event_type,
        "at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "payload": payload or {},
    }


async def emit(event_type: str, payload: dict[str, Any] | None = None) -> None:
    """Publish an event to every connected dashboard."""
    event = make_event(event_type, payload)
    logger.debug("event %s", event_type)
    await broadcaster.broadcast(event)


def emit_threadsafe(event_type: str, payload: dict[str, Any] | None = None) -> None:
    """Publish from sync code (schedules on the bound loop; buffers otherwise)."""
    event = make_event(event_type, payload)
    loop = broadcaster._loop  # noqa: SLF001 - internal by design
    if loop is not None and loop.is_running():
        with contextlib.suppress(RuntimeError):
            asyncio.run_coroutine_threadsafe(broadcaster.broadcast(event), loop)
            return
    broadcaster.recent.append(event)


def recent_events(event_type: str | None = None) -> list[dict[str, Any]]:
    events = list(broadcaster.recent)
    if event_type:
        return [e for e in events if e["type"] == event_type]
    return events
