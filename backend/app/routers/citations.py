"""GET /api/citations/{id} — resolve a citation id to its real source."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app import providers
from app.db import CitationCacheRow, read_session, session_scope
from app.db import cache_citation as store_citation
from app.schemas import Citation

router = APIRouter(prefix="/api", tags=["citations"])


@router.get("/citations/{citation_id:path}", response_model=Citation)
async def get_citation(citation_id: str) -> Citation:
    """Looks in the schemes worker's fact table first, then the local cache."""
    found = providers.citation_by_id(citation_id)
    if found is not None:
        with session_scope() as session:
            store_citation(session, found.model_dump(mode="json"))
        return found

    with read_session() as session:
        row = session.get(CitationCacheRow, citation_id)
        if row is not None and row.data:
            return Citation.model_validate(row.data)

    raise HTTPException(status_code=404, detail=f"No source on file for {citation_id}")
