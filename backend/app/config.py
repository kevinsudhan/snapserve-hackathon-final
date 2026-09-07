"""Application settings.

Reads the repo-root ``.env`` via pydantic-settings.  Keys that are missing from
``.env`` (SNAPSERVE_AGENT_ID, REVIEWER_PHONE, ...) are supplied as defaults here
so the file itself never needs editing.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

# backend/app/config.py -> backend/app -> backend -> <repo root>
APP_DIR = Path(__file__).resolve().parent
BACKEND_DIR = APP_DIR.parent
REPO_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    """Runtime configuration. Env var names are the upper-case field names."""

    model_config = SettingsConfigDict(
        env_file=str(REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- SnapServe -----------------------------------------------------
    snapserve_api_key: str = ""
    snapserve_base_url: str = "https://app.snapserve.ai/api"
    snapserve_agent_id: int = 1151
    ingest_all_agents: bool = False

    # --- Gemini --------------------------------------------------------
    google_api_key: str = ""
    gemini_text_model: str = "gemini-3.7-flash"
    gemini_fallback_models: str = "gemini-3.5-flash-lite,gemini-3.1-flash-lite,gemini-3.6-flash"
    gemini_live_model: str = "gemini-3.1-flash-live-preview"
    gemini_disabled: bool = False
    gemini_timeout_seconds: float = 30.0
    gemini_max_retries: int = 3

    # --- Agent shape (pushed by services/knowledge.py) -----------------
    reviewer_phone: str = "+918939153390"
    gemini_live_voice_name: str = "Charon"
    agent_language: str = ""  # blank => leave the agent's own `language` as-is
    agent_max_duration: int = 900
    agent_silence_timeout_seconds: int = 12

    # --- Server / web --------------------------------------------------
    backend_port: int = 8000
    dashboard_origin: str = "http://localhost:5173"
    public_base_url: str = "http://localhost:5173"

    # --- Paths (relative entries resolve against the repo root) --------
    data_dir: Path = Path("backend/data")
    db_path: Path = Path("backend/data/fasaldesk.db")
    evidence_dir: Path = Path("backend/data/evidence")
    prompts_dir: Path = Path("backend/prompts")

    # --- Pipeline behaviour --------------------------------------------
    poll_interval_seconds: float = 3.0
    poll_limit: int = 20
    poller_enabled: bool = True
    data_down_mode: bool = False
    evidence_token_ttl_days: int = 7
    max_upload_bytes: int = 15 * 1024 * 1024

    log_level: str = "INFO"

    @field_validator("data_dir", "db_path", "evidence_dir", "prompts_dir", mode="after")
    @classmethod
    def _absolutise(cls, value: Path) -> Path:
        return value if value.is_absolute() else (REPO_ROOT / value).resolve()

    @property
    def repo_root(self) -> Path:
        return REPO_ROOT

    @property
    def backend_dir(self) -> Path:
        return BACKEND_DIR

    @property
    def weather_snapshot_path(self) -> Path:
        return self.data_dir / "weather_snapshot.json"

    @property
    def gemini_ready(self) -> bool:
        return bool(self.google_api_key) and not self.gemini_disabled

    def ensure_dirs(self) -> None:
        """Create the writable directories the app needs."""
        for path in (self.data_dir, self.evidence_dir, self.db_path.parent):
            path.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_dirs()
    return settings


settings = get_settings()
