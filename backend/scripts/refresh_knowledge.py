"""Re-pull the weather/disaster snapshot, then re-render (and optionally push).

    python scripts/refresh_knowledge.py --days 60 --dry-run

This is the ONE place that touches Open-Meteo and GDACS: it shells out to the
data worker's CLI (``python -m services.knowledge_weather --days N``) and then
runs the same render/sync path as ``sync_agent.py``.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import subprocess
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.db import init_db  # noqa: E402
from services import knowledge  # noqa: E402

logger = logging.getLogger("refresh_knowledge")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Refresh the Araxys Desk knowledge snapshot")
    parser.add_argument("--days", type=int, default=60, help="days of history to pull (default 60)")
    parser.add_argument("--dry-run", action="store_true", help="render but do not push the agent")
    parser.add_argument("--skip-pull", action="store_true", help="re-render from the snapshot on disk")
    return parser.parse_args(argv)


def pull_snapshot(days: int) -> int:
    command = [sys.executable, "-m", "services.knowledge_weather", "--days", str(days)]
    logger.info("running %s", " ".join(command[1:]))
    process = subprocess.run(command, cwd=str(BACKEND_DIR), check=False)
    return process.returncode


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(name)s: %(message)s")
    init_db()

    if not args.skip_pull:
        code = pull_snapshot(args.days)
        if code != 0:
            logger.error("snapshot puller exited %s — keeping the previous snapshot", code)
            return code
        knowledge.mark_refreshed()

    result = asyncio.run(knowledge.push_to_snapserve(dry_run=args.dry_run))
    status = knowledge.knowledge_status()
    logger.info(
        "snapshot: %d districts, %d days, %d notable; prompt ~%d tokens; pushed=%s",
        status.districts,
        status.days,
        status.notable_events,
        status.approx_tokens,
        result["pushed"],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
