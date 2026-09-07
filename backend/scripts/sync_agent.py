"""Render the system prompt and sync SnapServe agent 1151.

    python scripts/sync_agent.py --dry-run   # write files only, touch nothing remote
    python scripts/sync_agent.py             # PATCH/PUT the live agent

Run from ``backend/`` with the project venv.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import settings  # noqa: E402
from app.db import init_db  # noqa: E402
from services import knowledge  # noqa: E402

logger = logging.getLogger("sync_agent")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render and push the FasalDesk agent prompt")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="render and write backend/data/rendered_prompt.md + agent_patch.json only",
    )
    parser.add_argument(
        "--json", action="store_true", help="print the result summary as JSON"
    )
    return parser.parse_args(argv)


async def run(dry_run: bool) -> dict:
    init_db()
    return await knowledge.push_to_snapserve(dry_run=dry_run)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(name)s: %(message)s")

    result = asyncio.run(run(args.dry_run))

    if args.json:
        sys.stdout.write(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
        return 0

    summary = result["summary"]
    lines = [
        f"agent      : {result['agent_id']} ({result.get('agent_name') or 'name unavailable'})",
        f"mode       : {'DRY RUN (nothing pushed)' if result['dry_run'] else 'PUSHED'}",
        f"prompt     : {result['prompt_path']}",
        f"patch      : {result['patch_path']}",
        f"prompt size: {summary['systemPrompt_chars']} chars "
        f"(~{summary['systemPrompt_approx_tokens']} tokens)",
        f"llm        : {summary['llmProvider']} / {summary['llmModel']}",
        f"voice      : {summary['voiceStack']} / {summary['geminiLiveVoiceName']}",
        f"language   : {summary['language']}",
        f"first turn : {summary['firstSpeaker']}, silence {summary['silenceTimeoutSeconds']}s, "
        f"max {summary['maxDuration']}s, recording {summary['recordingEnabled']}",
        f"tools      : {', '.join(summary['tools'])}",
        f"disposition: {', '.join(summary['dispositionSchema'])}",
        f"reviewer   : {settings.reviewer_phone}",
    ]
    if result.get("fetch_error"):
        lines.append(f"note       : could not read the live agent ({result['fetch_error'][:120]})")
    sys.stdout.write("\n".join(lines) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
