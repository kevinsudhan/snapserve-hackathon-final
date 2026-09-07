"""Shared pytest setup for the backend test suite.

Adds ``backend/`` to ``sys.path`` so tests can ``import services...`` when pytest
is run from the repository root, and makes the ``network`` marker opt-in.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def pytest_configure(config: pytest.Config) -> None:
    """Register the opt-in marker for tests that really call out to the internet."""
    config.addinivalue_line(
        "markers",
        "network: hits a real external API; skipped unless you run `pytest -m network`",
    )


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """Skip ``network`` tests unless the marker was asked for explicitly."""
    if "network" in (config.getoption("-m") or ""):
        return
    skip = pytest.mark.skip(reason="needs network; run `pytest -m network` to include")
    for item in items:
        if "network" in item.keywords:
            item.add_marker(skip)
