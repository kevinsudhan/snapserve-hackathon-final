"""FastAPI routers for the Araxys Desk backend."""

from app.routers import (  # noqa: F401
    admin,
    calls,
    citations,
    claims,
    evaluation,
    evidence,
    health,
    knowledge,
    stats,
    tickets,
    ws,
)

__all__ = [
    "admin",
    "calls",
    "citations",
    "claims",
    "evaluation",
    "evidence",
    "health",
    "knowledge",
    "stats",
    "tickets",
    "ws",
]
