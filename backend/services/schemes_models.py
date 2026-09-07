"""Pydantic models shared by the scheme/knowledge layer.

Field names are fixed by docs/CONTRACTS.md — do not rename them.
The core worker imports Citation, SchemeMatch and EvidenceItem from here.
"""

from __future__ import annotations

from typing import Literal, Optional, Union

from pydantic import BaseModel, Field

CitationKind = Literal["scheme", "weather", "disaster", "crop", "gazetteer", "other"]


class Citation(BaseModel):
    """A pointer to a real, checkable source for one spoken fact."""

    id: str
    title: str
    url: str
    publisher: str
    page: Optional[Union[int, str]] = None
    as_of: str
    quote: Optional[str] = None
    kind: CitationKind = "other"


class SchemeMatch(BaseModel):
    """One scheme fact that applies to a claim, with its citation."""

    fact_id: str
    scheme: str
    field: str
    text: str
    citation: Citation


class EvidenceItem(BaseModel):
    """One document or photo the farmer is asked to upload."""

    key: str
    label: str
    label_local: Optional[str] = None
    why: str
    citation_id: Optional[str] = None
    required: bool = True


class SchemeFact(BaseModel):
    """Raw entry as stored in backend/data/schemes.json."""

    id: str
    scheme: str
    field: str
    text: str
    applies_to: dict = Field(default_factory=dict)
    sensitivity: Literal["normal", "never_promise"] = "normal"
    citation: Citation
