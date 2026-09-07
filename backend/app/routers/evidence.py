"""Farmer-facing evidence endpoints (public: reached from a WhatsApp link)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.config import settings
from app.schemas import EvidenceFile, EvidencePage
from services import evidence as evidence_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/evidence", tags=["evidence"])


# NOTE: registered before /{token} so "files" is never read as a token.
@router.get("/files/{file_id}")
async def get_file(file_id: str) -> FileResponse:
    try:
        path, content_type, filename = evidence_service.file_path_for(file_id)
    except evidence_service.EvidenceError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileResponse(path, media_type=content_type, filename=filename)


@router.get("/{token}", response_model=EvidencePage)
async def get_page(token: str) -> EvidencePage:
    try:
        return await evidence_service.build_page(token)
    except evidence_service.EvidenceError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{token}/upload", response_model=EvidenceFile)
async def upload(
    token: str,
    item_key: str = Form(...),
    file: UploadFile = File(...),
    client_time: str | None = Form(None),
    lat: float | None = Form(None),
    lon: float | None = Form(None),
) -> EvidenceFile:
    data = await file.read()
    if len(data) > settings.max_upload_bytes:
        limit_mb = settings.max_upload_bytes // (1024 * 1024)
        raise HTTPException(status_code=413, detail=f"File larger than {limit_mb} MB")
    try:
        return await evidence_service.save_upload(
            token=token,
            item_key=item_key,
            filename=file.filename or "upload",
            content_type=file.content_type or "",
            data=data,
            client_time=client_time,
            lat=lat,
            lon=lon,
        )
    except evidence_service.EvidenceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
