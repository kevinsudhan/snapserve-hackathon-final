"""Async SnapServe REST client.

Base URL ``https://app.snapserve.ai/api`` with ``Authorization: Bearer <key>``.
The update verb for agents is undocumented, so :meth:`SnapServeClient.update_agent`
tries ``PATCH`` first, then ``PUT`` with the full merged object, and verifies the
result with a ``GET``.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

WEB_ORIGIN = "https://app.snapserve.ai"


class SnapServeError(RuntimeError):
    """Any non-recoverable SnapServe API failure."""


def absolute_recording_url(relative: str | None) -> Optional[str]:
    """``/api/storage/recordings/22845`` -> full https URL."""
    if not relative:
        return None
    if relative.startswith("http://") or relative.startswith("https://"):
        return relative
    return f"{WEB_ORIGIN}{relative if relative.startswith('/') else '/' + relative}"


class SnapServeClient:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = 20.0,
    ) -> None:
        self.api_key = api_key if api_key is not None else settings.snapserve_api_key
        self.base_url = (base_url or settings.snapserve_base_url).rstrip("/")
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    # -- plumbing -------------------------------------------------------
    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    async def __aenter__(self) -> "SnapServeClient":
        self._client = httpx.AsyncClient(
            base_url=self.base_url, headers=self._headers(), timeout=self.timeout
        )
        return self

    async def __aexit__(self, *_exc: Any) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        if not self.configured:
            raise SnapServeError("SNAPSERVE_API_KEY is not set")
        owned = self._client is None
        client = self._client or httpx.AsyncClient(
            base_url=self.base_url, headers=self._headers(), timeout=self.timeout
        )
        try:
            response = await client.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise SnapServeError(f"{method} {path} failed: {exc}") from exc
        finally:
            if owned:
                await client.aclose()
        return response

    async def _json(self, method: str, path: str, **kwargs: Any) -> Any:
        response = await self._request(method, path, **kwargs)
        if response.status_code >= 400:
            raise SnapServeError(
                f"{method} {path} -> HTTP {response.status_code}: {response.text[:300]}"
            )
        if not response.content:
            return None
        try:
            return response.json()
        except ValueError as exc:
            raise SnapServeError(f"{method} {path} returned non-JSON body") from exc

    @staticmethod
    def _as_list(payload: Any, *keys: str) -> list[dict]:
        """SnapServe list endpoints sometimes wrap the array in an envelope."""
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            for key in (*keys, "data", "items", "results"):
                value = payload.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]
        return []

    # -- agents ---------------------------------------------------------
    async def list_agents(self) -> list[dict]:
        return self._as_list(await self._json("GET", "/agents"), "agents")

    async def get_agent(self, agent_id: int | str) -> dict:
        payload = await self._json("GET", f"/agents/{agent_id}")
        if isinstance(payload, dict) and isinstance(payload.get("agent"), dict):
            return payload["agent"]
        if not isinstance(payload, dict):
            raise SnapServeError(f"GET /agents/{agent_id} returned {type(payload).__name__}")
        return payload

    async def update_agent(self, agent_id: int | str, patch: dict[str, Any]) -> dict:
        """Apply ``patch`` to an agent.

        Tries ``PATCH /agents/{id}`` with just the patch, then
        ``PUT /agents/{id}`` with the full merged object.  Verifies with a GET
        and logs which verb the API accepted.
        """
        current = await self.get_agent(agent_id)

        attempts: list[tuple[str, dict[str, Any]]] = [
            ("PATCH", patch),
            ("PUT", {**current, **patch}),
        ]
        last_error: str = "no attempt made"
        for verb, body in attempts:
            try:
                await self._json(verb, f"/agents/{agent_id}", json=body)
            except SnapServeError as exc:
                last_error = str(exc)
                logger.warning("agent update via %s rejected: %s", verb, last_error[:200])
                continue
            updated = await self.get_agent(agent_id)
            if self._patch_applied(updated, patch):
                logger.info("agent %s updated via %s", agent_id, verb)
                return updated
            last_error = f"{verb} accepted but the GET did not reflect the patch"
            logger.warning("agent %s: %s", agent_id, last_error)
        raise SnapServeError(f"could not update agent {agent_id}: {last_error}")

    @staticmethod
    def _patch_applied(agent: dict, patch: dict) -> bool:
        """Scalar keys must match; nested structures only need to be present."""
        for key, expected in patch.items():
            actual = agent.get(key)
            if isinstance(expected, (str, int, float, bool)) or expected is None:
                if actual != expected:
                    return False
            elif actual in (None, [], {}):
                return False
        return True

    # -- calls ----------------------------------------------------------
    async def list_calls(self, limit: int = 20) -> list[dict]:
        payload = await self._json("GET", "/calls", params={"limit": limit})
        return self._as_list(payload, "calls")

    async def get_call(self, call_id: int | str) -> dict:
        payload = await self._json("GET", f"/calls/{call_id}")
        if isinstance(payload, dict) and isinstance(payload.get("call"), dict):
            return payload["call"]
        if not isinstance(payload, dict):
            raise SnapServeError(f"GET /calls/{call_id} returned {type(payload).__name__}")
        return payload

    # -- health ---------------------------------------------------------
    async def ping(self) -> bool:
        if not self.configured:
            return False
        try:
            await self._json("GET", "/agents")
            return True
        except SnapServeError as exc:
            logger.debug("snapserve ping failed: %s", exc)
            return False


_default_client: Optional[SnapServeClient] = None


def get_client() -> SnapServeClient:
    """Process-wide client (no persistent connection until first request)."""
    global _default_client
    if _default_client is None:
        _default_client = SnapServeClient()
    return _default_client
