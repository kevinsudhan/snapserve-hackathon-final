"""SQLite persistence (SQLAlchemy 2.0).

Rich nested objects (transcripts, evidence blocks, risk, citations) are stored
as JSON columns — the pydantic models in :mod:`app.schemas` remain the schema of
record and the DB stays a thin, inspectable store.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    event,
    select,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from app.config import settings

logger = logging.getLogger(__name__)

# One writer at a time keeps SQLite happy when the poller, the ingest pipeline
# and HTTP handlers all touch the DB concurrently.
_write_lock = threading.RLock()


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def now_iso() -> str:
    return _now().isoformat()


class Base(DeclarativeBase):
    pass


class CallRow(Base):
    __tablename__ = "calls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    snapserve_call_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    agent_id: Mapped[Optional[int]] = mapped_column(Integer, default=None)
    direction: Mapped[str] = mapped_column(String(16), default="inbound")
    from_number: Mapped[Optional[str]] = mapped_column(String(32), default=None)
    to_number: Mapped[Optional[str]] = mapped_column(String(32), default=None)
    status: Mapped[str] = mapped_column(String(24), default="completed", index=True)
    started_at: Mapped[str] = mapped_column(String(32), default=now_iso)
    ended_at: Mapped[Optional[str]] = mapped_column(String(32), default=None)
    duration_seconds: Mapped[Optional[int]] = mapped_column(Integer, default=None)
    language_detected: Mapped[Optional[str]] = mapped_column(String(16), default=None)
    languages: Mapped[list] = mapped_column(JSON, default=list)
    code_switching: Mapped[bool] = mapped_column(Boolean, default=False)
    transcript: Mapped[list] = mapped_column(JSON, default=list)
    transcript_raw: Mapped[Optional[str]] = mapped_column(Text, default=None)
    summary: Mapped[Optional[str]] = mapped_column(Text, default=None)
    recording_url: Mapped[Optional[str]] = mapped_column(Text, default=None)
    claim_id: Mapped[Optional[int]] = mapped_column(Integer, default=None)
    ticket_id: Mapped[Optional[int]] = mapped_column(Integer, default=None)
    guardrail_incidents: Mapped[list] = mapped_column(JSON, default=list)
    processing: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    processing_error: Mapped[Optional[str]] = mapped_column(Text, default=None)
    raw: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[str] = mapped_column(String(32), default=now_iso)


class ClaimRow(Base):
    __tablename__ = "claims"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    reference: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    call_id: Mapped[int] = mapped_column(Integer, index=True)
    status: Mapped[str] = mapped_column(String(32), default="logged", index=True)
    farmer: Mapped[dict] = mapped_column(JSON, default=dict)
    crop: Mapped[Optional[str]] = mapped_column(String(64), default=None)
    land_extent: Mapped[Optional[dict]] = mapped_column(JSON, default=None)
    damage_type: Mapped[Optional[str]] = mapped_column(String(32), default=None)
    event_date: Mapped[Optional[str]] = mapped_column(String(16), default=None)
    event_date_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    location: Mapped[dict] = mapped_column(JSON, default=dict)
    narrative: Mapped[str] = mapped_column(Text, default="")
    weather_evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    disaster_evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    crop_evidence: Mapped[Optional[dict]] = mapped_column(JSON, default=None)
    scheme_matches: Mapped[list] = mapped_column(JSON, default=list)
    unknowns: Mapped[list] = mapped_column(JSON, default=list)
    evidence_required: Mapped[list] = mapped_column(JSON, default=list)
    risk: Mapped[dict] = mapped_column(JSON, default=dict)
    escalation_reason: Mapped[Optional[str]] = mapped_column(Text, default=None)
    farmer_explanation: Mapped[Optional[str]] = mapped_column(Text, default=None)
    reviewer_notes: Mapped[Optional[str]] = mapped_column(Text, default=None)
    agent_said_facts: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[str] = mapped_column(String(32), default=now_iso)
    updated_at: Mapped[str] = mapped_column(String(32), default=now_iso)


class TicketRow(Base):
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    claim_id: Mapped[int] = mapped_column(Integer, index=True)
    call_id: Mapped[int] = mapped_column(Integer, index=True)
    reference: Mapped[str] = mapped_column(String(32), index=True)
    severity: Mapped[str] = mapped_column(String(16), default="medium")
    reasons: Mapped[list] = mapped_column(JSON, default=list)
    farmer_explanation: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="open", index=True)
    reviewer_notes: Mapped[Optional[str]] = mapped_column(Text, default=None)
    created_at: Mapped[str] = mapped_column(String(32), default=now_iso)
    updated_at: Mapped[str] = mapped_column(String(32), default=now_iso)


class EvidenceTokenRow(Base):
    __tablename__ = "evidence_tokens"

    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    claim_id: Mapped[int] = mapped_column(Integer, index=True)
    created_at: Mapped[str] = mapped_column(String(32), default=now_iso)
    expires_at: Mapped[str] = mapped_column(String(32), default=now_iso)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)


class EvidenceFileRow(Base):
    __tablename__ = "evidence_files"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    claim_id: Mapped[int] = mapped_column(Integer, index=True)
    item_key: Mapped[str] = mapped_column(String(64), default="other")
    filename: Mapped[str] = mapped_column(String(255), default="")
    content_type: Mapped[str] = mapped_column(String(64), default="")
    size: Mapped[int] = mapped_column(Integer, default=0)
    path: Mapped[str] = mapped_column(Text, default="")
    uploaded_at: Mapped[str] = mapped_column(String(32), default=now_iso)
    client_time: Mapped[Optional[str]] = mapped_column(String(32), default=None)
    lat: Mapped[Optional[float]] = mapped_column(Float, default=None)
    lon: Mapped[Optional[float]] = mapped_column(Float, default=None)
    quality_flag: Mapped[str] = mapped_column(String(16), default="unchecked")
    exif: Mapped[dict] = mapped_column(JSON, default=dict)


class CitationCacheRow(Base):
    __tablename__ = "citations_cache"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[str] = mapped_column(String(32), default=now_iso)


class GuardrailIncidentRow(Base):
    __tablename__ = "guardrail_incidents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    call_id: Mapped[int] = mapped_column(Integer, index=True)
    claim_id: Mapped[Optional[int]] = mapped_column(Integer, default=None, index=True)
    turn_index: Mapped[int] = mapped_column(Integer, default=-1)
    category: Mapped[str] = mapped_column(String(32), default="other", index=True)
    text: Mapped[str] = mapped_column(Text, default="")
    severity: Mapped[str] = mapped_column(String(16), default="medium")
    detector: Mapped[str] = mapped_column(String(16), default="rules")
    created_at: Mapped[str] = mapped_column(String(32), default=now_iso)


class KnowledgeMetaRow(Base):
    __tablename__ = "knowledge_meta"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON, default=None)
    updated_at: Mapped[str] = mapped_column(String(32), default=now_iso)


class EvalRunRow(Base):
    __tablename__ = "eval_runs"

    run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    started_at: Mapped[str] = mapped_column(String(32), default=now_iso)
    finished_at: Mapped[Optional[str]] = mapped_column(String(32), default=None)
    status: Mapped[str] = mapped_column(String(16), default="running")
    data: Mapped[dict] = mapped_column(JSON, default=dict)


# --------------------------------------------------------------------------
# engine / session
# --------------------------------------------------------------------------
_engine = create_engine(
    f"sqlite:///{settings.db_path}",
    future=True,
    connect_args={"check_same_thread": False, "timeout": 30},
)


@event.listens_for(_engine, "connect")
def _sqlite_pragmas(dbapi_connection, _record) -> None:  # pragma: no cover - driver hook
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False, future=True)


def init_db() -> None:
    settings.ensure_dirs()
    Base.metadata.create_all(_engine)
    logger.info("database ready at %s", settings.db_path)


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transactional session. Writes are serialised through a process lock."""
    with _write_lock:
        session = SessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


@contextmanager
def read_session() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def get_db() -> Iterator[Session]:
    """FastAPI dependency."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


# --------------------------------------------------------------------------
# small helpers used across services
# --------------------------------------------------------------------------
def meta_get(key: str, default: Any = None) -> Any:
    with read_session() as session:
        row = session.get(KnowledgeMetaRow, key)
        return row.value if row is not None else default


def meta_set(key: str, value: Any) -> None:
    with session_scope() as session:
        row = session.get(KnowledgeMetaRow, key)
        if row is None:
            session.add(KnowledgeMetaRow(key=key, value=value, updated_at=now_iso()))
        else:
            row.value = value
            row.updated_at = now_iso()


def next_reference(session: Session) -> str:
    """``VST-<year>-<0001>`` — sequential within the calendar year."""
    year = _now().year
    prefix = f"VST-{year}-"
    rows = session.scalars(
        select(ClaimRow.reference).where(ClaimRow.reference.like(f"{prefix}%"))
    ).all()
    highest = 0
    for ref in rows:
        tail = ref.rsplit("-", 1)[-1]
        if tail.isdigit():
            highest = max(highest, int(tail))
    return f"{prefix}{highest + 1:04d}"


def cache_citation(session: Session, citation: dict) -> None:
    cid = citation.get("id")
    if not cid:
        return
    row = session.get(CitationCacheRow, cid)
    if row is None:
        session.add(CitationCacheRow(id=cid, data=citation, updated_at=now_iso()))
    else:
        row.data = citation
        row.updated_at = now_iso()
