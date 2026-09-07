"""Thin wrapper around the ``google-genai`` SDK (Gemini API, not Vertex).

Everything the backend asks Gemini for is *structured*: a pydantic
``response_schema`` plus ``response_mime_type="application/json"``.  Set
``GEMINI_DISABLED=1`` (or leave ``GOOGLE_API_KEY`` empty) and every call returns
``None`` so the callers fall back to their deterministic paths — that is how the
offline tests run the full pipeline.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional, TypeVar

from pydantic import BaseModel

from app.config import settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

_client: Any = None
_client_failed = False


def is_available() -> bool:
    """True when Gemini calls are permitted (key present, not disabled)."""
    return settings.gemini_ready and not _client_failed


def _get_client() -> Any:
    """Lazily build the SDK client; returns None when unusable."""
    global _client, _client_failed
    if _client is not None:
        return _client
    if _client_failed or not settings.gemini_ready:
        return None
    try:
        from google import genai
        from google.genai import types as genai_types

        _client = genai.Client(
            api_key=settings.google_api_key,
            http_options=genai_types.HttpOptions(
                timeout=int(settings.gemini_timeout_seconds * 1000)
            ),
        )
    except Exception as exc:  # pragma: no cover - SDK/env problem
        _client_failed = True
        logger.warning("gemini client unavailable: %s", exc.__class__.__name__)
        return None
    return _client


def reset_client() -> None:
    """Drop the cached client (used by tests that flip settings)."""
    global _client, _client_failed
    _client = None
    _client_failed = False


async def generate_json(
    prompt: str,
    schema: type[T],
    *,
    system_instruction: str | None = None,
    model: str | None = None,
    temperature: float = 0.1,
) -> Optional[T]:
    """Ask Gemini for JSON matching ``schema``. Returns None if unavailable."""
    client = _get_client()
    if client is None:
        logger.debug("gemini disabled — skipping structured call")
        return None

    from google.genai import types as genai_types

    config = genai_types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=schema,
        temperature=temperature,
        system_instruction=system_instruction,
    )
    primary = model or settings.gemini_text_model
    fallbacks = [m.strip() for m in settings.gemini_fallback_models.split(",") if m.strip()]
    model_chain = [primary] + [m for m in fallbacks if m != primary]

    last_error: Exception | None = None
    for attempt in range(settings.gemini_max_retries + 1):
        # rotate through the model chain: quota (429) / overload (503) on one model
        # should not take the whole pipeline down
        model_name = model_chain[attempt % len(model_chain)]
        try:
            response = await asyncio.wait_for(
                client.aio.models.generate_content(
                    model=model_name, contents=prompt, config=config
                ),
                timeout=settings.gemini_timeout_seconds,
            )
        except asyncio.TimeoutError as exc:
            last_error = exc
            logger.warning("gemini timeout (attempt %d/%d)", attempt + 1, settings.gemini_max_retries + 1)
        except Exception as exc:
            last_error = exc
            logger.warning(
                "gemini error %s on %s (attempt %d/%d)",
                exc.__class__.__name__,
                model_name,
                attempt + 1,
                settings.gemini_max_retries + 1,
            )
        else:
            parsed = getattr(response, "parsed", None)
            if isinstance(parsed, schema):
                return parsed
            text = getattr(response, "text", None)
            if text:
                try:
                    return schema.model_validate_json(text)
                except Exception as exc:
                    last_error = exc
                    logger.warning("gemini returned unparseable JSON for %s", schema.__name__)
            else:
                last_error = RuntimeError("empty response")
        if attempt < settings.gemini_max_retries:
            await asyncio.sleep(0.6 * (attempt + 1))

    logger.warning(
        "gemini structured call for %s gave up: %s", schema.__name__, last_error.__class__.__name__
        if last_error else "unknown"
    )
    return None


async def generate_text(
    prompt: str,
    *,
    system_instruction: str | None = None,
    model: str | None = None,
    temperature: float = 0.2,
) -> Optional[str]:
    """Free-text generation. Returns None if unavailable or on failure."""
    client = _get_client()
    if client is None:
        return None

    from google.genai import types as genai_types

    config = genai_types.GenerateContentConfig(
        temperature=temperature, system_instruction=system_instruction
    )
    try:
        response = await asyncio.wait_for(
            client.aio.models.generate_content(
                model=model or settings.gemini_text_model, contents=prompt, config=config
            ),
            timeout=settings.gemini_timeout_seconds,
        )
    except Exception as exc:
        logger.warning("gemini text call failed: %s", exc.__class__.__name__)
        return None
    text = getattr(response, "text", None)
    return text.strip() if text else None


def load_prompt(name: str) -> str:
    """Read a prompt template from ``backend/prompts``."""
    path = settings.prompts_dir / name
    if not path.exists():
        logger.warning("prompt file %s missing", path)
        return ""
    return path.read_text(encoding="utf-8")
