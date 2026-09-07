"""Knowledge base: snapshot status, refresh, geo, snapshot, rendered prompt."""

from __future__ import annotations

import asyncio
import json
import logging
import sys

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse

from app import providers
from app.config import settings
from app.events import emit
from app.schemas import KnowledgeStatus, PromptResponse, WeatherSnapshot
from services import knowledge as knowledge_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])

REFRESH_TIMEOUT_SECONDS = 900


@router.get("/status", response_model=KnowledgeStatus)
async def status() -> KnowledgeStatus:
    return knowledge_service.knowledge_status()


@router.get("/prompt", response_model=PromptResponse)
async def prompt() -> PromptResponse:
    rendered = knowledge_service.render_system_prompt()
    return PromptResponse(
        system_prompt=rendered, approx_tokens=knowledge_service.approx_tokens(rendered)
    )


@router.get("/snapshot")
async def snapshot() -> JSONResponse:
    """The snapshot exactly as it sits on disk (nothing is trimmed away)."""
    path = settings.weather_snapshot_path
    if path.exists():
        try:
            return JSONResponse(json.loads(path.read_text(encoding="utf-8")))
        except ValueError:
            logger.warning("weather_snapshot.json is not valid JSON — falling back")

    loaded = providers.load_snapshot()
    if loaded is None:
        raise HTTPException(
            status_code=404,
            detail="No weather snapshot on file. Run POST /api/knowledge/refresh.",
        )
    return JSONResponse(loaded.model_dump(mode="json"))


@router.get("/geo")
async def geo() -> JSONResponse:
    path = settings.data_dir / "tn_districts.geojson"
    if not path.exists():
        raise HTTPException(status_code=404, detail="tn_districts.geojson is not on file yet")
    try:
        return JSONResponse(json.loads(path.read_text(encoding="utf-8")))
    except ValueError as exc:
        raise HTTPException(status_code=500, detail="tn_districts.geojson is not valid JSON") from exc


async def _run_snapshot_cli(days: int) -> tuple[int, str]:
    """``python -m services.knowledge_weather --days N`` from ``backend/``."""
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "services.knowledge_weather",
        "--days",
        str(days),
        cwd=str(settings.backend_dir),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    try:
        stdout, _ = await asyncio.wait_for(process.communicate(), timeout=REFRESH_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        process.kill()
        return 1, "snapshot puller timed out"
    return process.returncode or 0, (stdout or b"").decode("utf-8", "replace")[-4000:]


@router.post("/refresh", response_model=KnowledgeStatus)
async def refresh(
    days: int = Query(60, ge=1, le=92),
    push: bool = Query(True, description="Also push the re-rendered prompt to the agent"),
) -> KnowledgeStatus:
    """Re-pull the 60-day snapshot (the one network call), re-render, re-push."""
    code, output = await _run_snapshot_cli(days)
    if code != 0:
        logger.warning("snapshot puller exited %s: %s", code, output[-500:])
        raise HTTPException(
            status_code=502,
            detail="The snapshot puller failed; the previous snapshot is unchanged.",
        )

    knowledge_service.mark_refreshed()
    try:
        result = await knowledge_service.push_to_snapserve(dry_run=not push)
    except Exception as exc:
        logger.warning("prompt push failed after refresh: %s", exc)
        result = {"pushed": False, "error": str(exc)}

    current = knowledge_service.knowledge_status()
    await emit(
        "knowledge.refreshed",
        {
            "days": days,
            "pushed": bool(result.get("pushed")),
            "status": current.model_dump(mode="json"),
        },
    )
    return current


@router.get("/documents/tn-kharif-2026-sum-insured", response_class=HTMLResponse)
async def simulated_sum_insured_document() -> HTMLResponse:
    """Serve the SIMULATED Tamil Nadu Kharif 2026 sum-insured notification (citation N1)."""
    from services import sum_insured

    return HTMLResponse(sum_insured.render_html())


@router.get("/documents/tn-kharif-2026-sum-insured.json")
async def simulated_sum_insured_json() -> JSONResponse:
    from services import sum_insured

    return JSONResponse(sum_insured.load())
