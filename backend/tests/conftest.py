"""Test-scoped setup for the backend suite.

``backend/conftest.py`` only puts ``backend/`` on ``sys.path``; this file pins the
test process to an offline sandbox — no Gemini calls, no SnapServe polling, a
throwaway SQLite file — and provides the shared fixtures.

The environment has to be set here, before any test module imports
``app.config``, because ``settings`` is a module-level singleton read at import
time.  Fixtures are opt-in (nothing is autouse) so other workers' tests are
unaffected.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

_SANDBOX = Path(tempfile.mkdtemp(prefix="araxysdesk-tests-"))

# Offline defaults. DATA_DIR deliberately still points at the real backend/data
# so the suite exercises the real snapshot, schemes and district files.
os.environ.setdefault("GEMINI_DISABLED", "1")
os.environ.setdefault("POLLER_ENABLED", "false")
os.environ.setdefault("DB_PATH", str(_SANDBOX / "araxysdesk-test.db"))
os.environ.setdefault("EVIDENCE_DIR", str(_SANDBOX / "evidence"))
os.environ.setdefault("PUBLIC_BASE_URL", "http://192.168.1.50:5173")
os.environ.setdefault("DATA_DOWN_MODE", "false")


def pytest_sessionfinish(session, exitstatus) -> None:  # noqa: ARG001
    shutil.rmtree(_SANDBOX, ignore_errors=True)


@pytest.fixture
def sandbox_dir() -> Path:
    """Throwaway directory for this test session."""
    return _SANDBOX


@pytest.fixture
def clean_db():
    """Empty every core table and the event buffer."""
    from sqlalchemy import delete

    from app.config import settings
    from app.db import (
        CallRow,
        ClaimRow,
        EvidenceFileRow,
        EvidenceTokenRow,
        GuardrailIncidentRow,
        KnowledgeMetaRow,
        TicketRow,
        init_db,
        session_scope,
    )
    from app.events import broadcaster

    init_db()
    models = (
        GuardrailIncidentRow,
        EvidenceFileRow,
        EvidenceTokenRow,
        TicketRow,
        ClaimRow,
        CallRow,
        KnowledgeMetaRow,
    )
    with session_scope() as db:
        for model in models:
            db.execute(delete(model))
    broadcaster.clear()
    settings.data_down_mode = False
    yield
    broadcaster.clear()


@pytest.fixture
def client(clean_db):
    """FastAPI TestClient with the app lifespan running (poller disabled)."""
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client
