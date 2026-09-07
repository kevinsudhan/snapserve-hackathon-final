"""Background poller: SnapServe ``GET /calls`` -> local CallRecords -> ingest.

The backend never needs a public URL; it pulls.  Every ``POLL_INTERVAL_SECONDS``
we fetch the newest calls, insert anything unseen, emit ``call.started`` for
calls still running (detected by the absence of ``endedAt``) and ``call.completed``
plus an ingest job for finished calls that carry a transcript.

API failures are logged and retried on the next tick — the loop never dies.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from typing import Any, Optional

from sqlalchemy import select

from app.config import settings
from app.db import CallRow, meta_get, meta_set, now_iso, session_scope
from app.events import emit
from app.schemas import PollerStatus
from app.serializers import call_to_schema
from services.snapserve import SnapServeClient, SnapServeError, absolute_recording_url, get_client

logger = logging.getLogger(__name__)

CURSOR_KEY = "poller.cursor"
LAST_POLL_KEY = "poller.last_poll_at"
RESET_KEY = "poller.reset_at"

_TERMINAL_FAILED = {"failed", "error", "errored", "canceled", "cancelled"}
_TERMINAL_NO_PICKUP = {"no_pickup", "no-pickup", "no_answer", "no-answer", "noanswer",
                       "missed", "busy", "rejected", "declined"}
_IN_PROGRESS = {"in_progress", "in-progress", "inprogress", "ongoing", "ringing",
                "queued", "initiated", "dialing", "active", "started"}


def map_status(raw_status: Any, ended_at: Any) -> str:
    """Normalise SnapServe's status vocabulary onto the contract's four values."""
    status = str(raw_status or "").strip().lower()
    if status in _TERMINAL_FAILED:
        return "failed"
    if status in _TERMINAL_NO_PICKUP:
        return "no_pickup"
    if status in _IN_PROGRESS:
        return "in_progress"
    if status == "completed":
        return "completed"
    # unknown vocabulary: an unfinished call has no endedAt
    return "completed" if ended_at else "in_progress"


def map_direction(payload: dict, metadata: dict) -> str:
    raw = str(payload.get("direction") or metadata.get("direction") or "").lower()
    if "out" in raw:
        return "outbound"
    if "web" in raw:
        return "webcall"
    if "in" in raw:
        return "inbound"
    return "inbound"


def parse_metadata(raw: Any) -> dict:
    """``metadata`` arrives as a JSON *string*."""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except ValueError:
            return {}
    return {}


def call_fields(payload: dict) -> dict:
    """SnapServe call JSON -> CallRow kwargs."""
    metadata = parse_metadata(payload.get("metadata"))
    ended_at = payload.get("endedAt")
    transcript = payload.get("transcript") or ""
    if not isinstance(transcript, str):
        transcript = str(transcript)
    return {
        "snapserve_call_id": str(payload.get("id")),
        "agent_id": payload.get("agentId"),
        "direction": map_direction(payload, metadata),
        "from_number": payload.get("fromNumber"),
        "to_number": payload.get("toNumber"),
        "status": map_status(payload.get("status"), ended_at),
        "started_at": str(payload.get("createdAt") or now_iso()),
        "ended_at": str(ended_at) if ended_at else None,
        "duration_seconds": payload.get("durationSeconds"),
        "transcript_raw": transcript,
        "summary": payload.get("callSummary"),
        "recording_url": absolute_recording_url(payload.get("recordingUrl")),
        "raw": {
            "metadata": metadata,
            "dispositionResult": payload.get("dispositionResult"),
            "agentName": payload.get("agentName"),
            "status": payload.get("status"),
        },
    }


class Poller:
    """Owns the poll loop and a serial ingest worker."""

    def __init__(self, client: Optional[SnapServeClient] = None) -> None:
        self.client = client or get_client()
        self.running = False
        self.last_poll_at: Optional[str] = meta_get(LAST_POLL_KEY)
        self.last_error: Optional[str] = None
        self.polls = 0
        self._task: Optional[asyncio.Task] = None
        self._worker: Optional[asyncio.Task] = None
        self._queue: asyncio.Queue[int] = asyncio.Queue()
        self._queued: set[int] = set()

    # -- lifecycle ------------------------------------------------------
    async def start(self) -> None:
        if self._task is not None:
            return
        self.running = True
        self._worker = asyncio.create_task(self._ingest_worker(), name="ingest-worker")
        self._task = asyncio.create_task(self._loop(), name="snapserve-poller")
        logger.info(
            "poller started (every %.1fs, agent %s)",
            settings.poll_interval_seconds,
            "any" if settings.ingest_all_agents else settings.snapserve_agent_id,
        )

    async def stop(self) -> None:
        self.running = False
        for task in (self._task, self._worker):
            if task is not None:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
        self._task = None
        self._worker = None
        await self.client.aclose()
        logger.info("poller stopped")

    def status(self) -> PollerStatus:
        return PollerStatus(
            running=self.running,
            last_poll_at=self.last_poll_at,
            last_error=self.last_error,
            polls=self.polls,
        )

    # -- loops ----------------------------------------------------------
    async def _loop(self) -> None:
        while self.running:
            try:
                await self.poll_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # pragma: no cover - the loop must survive
                self.last_error = f"{exc.__class__.__name__}: {exc}"
                logger.warning("poll tick failed: %s", self.last_error)
            await asyncio.sleep(max(0.5, settings.poll_interval_seconds))

    async def _ingest_worker(self) -> None:
        from services import ingest

        while True:
            call_id = await self._queue.get()
            try:
                await ingest.process_call(call_id)
            except asyncio.CancelledError:
                raise
            except Exception:  # pragma: no cover - ingest logs its own errors
                logger.exception("ingest worker failed for call %s", call_id)
            finally:
                self._queued.discard(call_id)
                self._queue.task_done()

    def enqueue(self, call_id: int) -> None:
        if call_id in self._queued:
            return
        self._queued.add(call_id)
        self._queue.put_nowait(call_id)

    # -- one tick -------------------------------------------------------
    async def poll_once(self) -> int:
        """Fetch the newest calls and reconcile them. Returns rows touched."""
        if not self.client.configured:
            self.last_error = "SNAPSERVE_API_KEY not set"
            return 0
        try:
            payloads = await self.client.list_calls(limit=settings.poll_limit)
        except SnapServeError as exc:
            self.last_error = str(exc)
            logger.warning("snapserve poll failed: %s", str(exc)[:200])
            return 0

        self.polls += 1
        self.last_poll_at = now_iso()
        self.last_error = None
        meta_set(LAST_POLL_KEY, self.last_poll_at)

        touched = 0
        newest_seen: Optional[str] = None
        reset_at = meta_get(RESET_KEY)
        # oldest first so ids and events arrive in chronological order
        for payload in reversed(payloads):
            if not isinstance(payload, dict) or payload.get("id") is None:
                continue
            if not settings.ingest_all_agents:
                agent_id = payload.get("agentId")
                if agent_id is not None and int(agent_id) != settings.snapserve_agent_id:
                    continue
            if reset_at and str(payload.get("createdAt") or "") < str(reset_at):
                continue  # cleared by /api/admin/reset-demo
            newest_seen = str(payload.get("id"))
            if await self._reconcile(payload):
                touched += 1

        if newest_seen:
            meta_set(CURSOR_KEY, newest_seen)
        await emit("poller.status", self.status().model_dump(mode="json"))
        return touched

    async def _reconcile(self, payload: dict) -> bool:
        """Insert or update one call; emit + enqueue as its state changes."""
        fields = call_fields(payload)
        snapserve_id = fields["snapserve_call_id"]

        with session_scope() as session:
            row = session.scalar(
                select(CallRow).where(CallRow.snapserve_call_id == snapserve_id)
            )
            is_new = row is None
            previous_status = None if row is None else row.status
            had_transcript = bool(row.transcript_raw) if row is not None else False

            if row is None:
                row = CallRow(**fields, created_at=now_iso())
                session.add(row)
            else:
                for key, value in fields.items():
                    if key == "transcript_raw" and not value and row.transcript_raw:
                        continue  # never blank an existing transcript
                    setattr(row, key, value)
            session.flush()

            call_id = row.id
            status = row.status
            transcript_present = bool(row.transcript_raw and row.transcript_raw.strip())
            processing = row.processing
            record = call_to_schema(row)

        changed = is_new or previous_status != status or (transcript_present and not had_transcript)
        if not changed:
            return False

        if status == "in_progress":
            await emit("call.started", record.model_dump(mode="json"))
            return True

        if status == "completed" and transcript_present:
            await emit("call.completed", record.model_dump(mode="json"))
            if processing == "pending":
                self.enqueue(call_id)
            return True

        if status in ("failed", "no_pickup"):
            await emit("call.completed", record.model_dump(mode="json"))
            return True

        return True


_poller: Optional[Poller] = None


def get_poller() -> Poller:
    global _poller
    if _poller is None:
        _poller = Poller()
    return _poller


def poller_status() -> PollerStatus:
    if _poller is None:
        return PollerStatus(running=False, last_poll_at=meta_get(LAST_POLL_KEY))
    return _poller.status()
