"""Prompt assembly and the SnapServe agent patch.

The agent makes **no tool calls**, so everything it is allowed to say has to be
baked into its system prompt: scheme facts, the weather snapshot, the crop
calendar, evidence checklists and the safe scripts — each carrying citation ids
that resolve in the CRM.

``render_system_prompt()`` fills the placeholders in
``prompts/system_prompt.md`` (owned by the schemes worker).  If that file has not
landed yet a minimal built-in placeholder is used so the pipeline still renders.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from app import providers
from app.config import settings
from app.db import meta_get, meta_set, now_iso
from app.schemas import Citation, KnowledgeStatus

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))

PLACEHOLDERS = (
    "SCHEME_KNOWLEDGE",
    "WEATHER_KNOWLEDGE",
    "CROP_CALENDAR",
    "EVIDENCE_CHECKLISTS",
    "SAFE_SCRIPTS",
    "REVIEWER_PHONE",
    "GENERATED_AT",
)

LAST_REFRESH_KEY = "knowledge.last_refresh_at"
AGENT_SYNCED_KEY = "knowledge.agent_synced_at"

GREETING = (
    "Hello, this is Sunil from the crop insurance help desk — please speak in "
    "whichever language you are most comfortable with, and tell me what happened "
    "to your crop."
)

INACTIVITY_MESSAGE = "Are you still there? Take your time, I am listening."

WARM_HANDOFF_MESSAGE = (
    "I am connecting you to a reviewer now. I will tell them what you have told me "
    "so you do not have to repeat it."
)

TRANSFER_SUMMARY_PROMPT = (
    "In three sentences, tell the reviewer: the caller's name and village, the crop "
    "and the damage they described with the date, and why the call is being "
    "transferred. State only what the caller said. Do not add any opinion about "
    "whether the claim is valid."
)

_FALLBACK_PROMPT = """# Sunil — crop insurance intake (placeholder prompt)

You are Sunil, a calm intake assistant for crop-damage insurance claims in
{{REVIEWER_PHONE}}'s review desk. Speak the caller's language. Ask one question at
a time. Never promise money, approval, or a date. If asked about an amount,
approval, or timing, say you cannot decide it and that a reviewer will confirm.
State only the facts below, each of which carries a citation id. If something is
not below, say you do not know.

Generated: {{GENERATED_AT}}

## Scheme facts
{{SCHEME_KNOWLEDGE}}

## Weather record
{{WEATHER_KNOWLEDGE}}

## Crop calendar
{{CROP_CALENDAR}}

## Evidence checklists
{{EVIDENCE_CHECKLISTS}}

## Safe scripts
{{SAFE_SCRIPTS}}
"""

_DAMAGE_TYPES = [
    "cyclone", "flood", "inundation", "heavy_rain", "unseasonal_rain", "drought",
    "hailstorm", "pest", "disease", "fire", "landslide", "other",
]


# --------------------------------------------------------------------------
# rendering
# --------------------------------------------------------------------------
def approx_tokens(text: str) -> int:
    """Rough token count — four characters per token."""
    return len(text or "") // 4


def generated_at_ist() -> str:
    now = datetime.now(IST)
    return now.strftime("%A, %d %B %Y %H:%M IST")


def render_evidence_checklists() -> str:
    """One block per distinct checklist, with the damage types that share it."""
    grouped: dict[tuple, list[str]] = {}
    for damage in _DAMAGE_TYPES:
        items = providers.evidence_checklist(damage, None)
        key = tuple((item.key, item.label, item.required) for item in items)
        grouped.setdefault(key, []).append(damage)

    blocks: list[str] = []
    for key, damages in grouped.items():
        header = "any damage" if len(damages) == len(_DAMAGE_TYPES) else ", ".join(damages)
        lines = [f"For {header}:"]
        for item_key, label, required in key:
            marker = "required" if required else "helpful"
            lines.append(f"  - {label} ({marker}) [{item_key}]")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def render_safe_scripts() -> str:
    scripts = providers.safe_scripts()
    if not scripts:
        return ""
    lines: list[str] = []
    for name, body in scripts.items():
        if isinstance(body, dict):
            text = body.get("en") or body.get("text") or next(
                (v for v in body.values() if isinstance(v, str)), ""
            )
            guidance = body.get("guidance")
        else:
            text, guidance = str(body), None
        lines.append(f"- **{name}**: {text}")
        if guidance:
            lines.append(f"  (delivery: {guidance})")
    lines.append(
        "  Render these in the caller's own language and register; keep the meaning "
        "exactly, never add an amount, an approval, or a date."
    )
    return "\n".join(lines)


def load_prompt_template() -> tuple[str, bool]:
    """(template text, came_from_file)."""
    path = settings.prompts_dir / "system_prompt.md"
    if path.exists():
        text = path.read_text(encoding="utf-8")
        if text.strip():
            return text, True
    logger.warning(
        "prompts/system_prompt.md not present yet — rendering the built-in placeholder"
    )
    return _FALLBACK_PROMPT, False


def render_system_prompt() -> str:
    """Fill every placeholder in the system prompt template."""
    template, from_file = load_prompt_template()
    snapshot = providers.load_snapshot()

    values = {
        "SCHEME_KNOWLEDGE": providers.render_scheme_knowledge()
        or "(No scheme facts are loaded. Say you do not have the scheme detail.)",
        "WEATHER_KNOWLEDGE": providers.render_weather_knowledge(snapshot)
        or "(No weather snapshot is loaded. Do not state any weather figure.)",
        "CROP_CALENDAR": providers.crop_calendar_text()
        or "(No crop calendar is loaded. Do not state sowing or harvest windows.)",
        "EVIDENCE_CHECKLISTS": render_evidence_checklists(),
        "SAFE_SCRIPTS": render_safe_scripts(),
        "REVIEWER_PHONE": settings.reviewer_phone,
        "GENERATED_AT": generated_at_ist(),
    }

    rendered = template
    for name in PLACEHOLDERS:
        rendered = rendered.replace("{{" + name + "}}", values[name])

    missing = [name for name in PLACEHOLDERS if "{{" + name + "}}" in rendered]
    if missing:  # pragma: no cover - defensive
        logger.warning("placeholders left unfilled: %s", ", ".join(missing))
    if from_file:
        logger.info("system prompt rendered (~%d tokens)", approx_tokens(rendered))
    return rendered


# --------------------------------------------------------------------------
# agent patch
# --------------------------------------------------------------------------
def disposition_schema() -> list[dict[str, Any]]:
    return [
        {"key": "crop", "label": "Crop", "type": "text", "required": False},
        {"key": "land_extent", "label": "Land extent (with unit)", "type": "text", "required": False},
        {"key": "damage_type", "label": "Damage type", "type": "choice",
         "options": _DAMAGE_TYPES, "required": False},
        {"key": "event_date", "label": "Date of damage", "type": "text", "required": False},
        {"key": "village", "label": "Village", "type": "text", "required": False},
        {"key": "district", "label": "District", "type": "text", "required": False},
        {"key": "outcome", "label": "Outcome", "type": "choice",
         "options": ["logged", "escalated", "incomplete"], "required": True},
    ]


def transfer_tool() -> dict[str, Any]:
    return {
        "type": "call_transfer",
        "name": "transfer_to_reviewer",
        "description": (
            "Transfer the caller to a human reviewer when they ask for a person, "
            "when they are distressed, or when the details cannot be settled on the call."
        ),
        "transferTo": settings.reviewer_phone,
        "transferMode": "warm_summary",
        "warmHandoffMessage": WARM_HANDOFF_MESSAGE,
        "summaryPrompt": TRANSFER_SUMMARY_PROMPT,
    }


def end_call_tool() -> dict[str, Any]:
    return {
        "type": "end_call",
        "name": "end_call",
        "description": "End the call once the caller has their reference number and next steps.",
    }


def merge_tools(existing: list | None) -> list[dict[str, Any]]:
    """Keep the agent's ``end_call``; ensure exactly one reviewer transfer tool."""
    tools: list[dict[str, Any]] = []
    for tool in existing or []:
        if not isinstance(tool, dict):
            continue
        kind = str(tool.get("type") or "")
        if kind == "call_transfer":
            continue  # replaced below
        tools.append(tool)
    if not any(str(t.get("type")) == "end_call" for t in tools):
        tools.append(end_call_tool())
    tools.append(transfer_tool())
    return tools


def build_agent_patch(
    system_prompt: str, current_agent: Optional[dict] = None
) -> dict[str, Any]:
    """The exact JSON body we send to SnapServe for agent 1151."""
    patch: dict[str, Any] = {
        "systemPrompt": system_prompt,
        "llmProvider": "google",
        "llmModel": settings.gemini_live_model,
        "voiceStack": "gemini_live",
        "geminiLiveVoiceName": settings.gemini_live_voice_name,
        "greetingMessage": GREETING,
        "firstSpeaker": "assistant",
        "silenceTimeoutSeconds": settings.agent_silence_timeout_seconds,
        "inactivityMessage": INACTIVITY_MESSAGE,
        "maxDuration": settings.agent_max_duration,
        "recordingEnabled": True,
        "dispositionSchema": disposition_schema(),
        "tools": merge_tools((current_agent or {}).get("tools")),
    }
    if settings.agent_language:
        patch["language"] = settings.agent_language
    return patch


def patch_summary(patch: dict[str, Any]) -> dict[str, Any]:
    """Log/report-friendly view — never echoes the whole prompt."""
    prompt = patch.get("systemPrompt", "")
    return {
        "systemPrompt_chars": len(prompt),
        "systemPrompt_approx_tokens": approx_tokens(prompt),
        "llmProvider": patch.get("llmProvider"),
        "llmModel": patch.get("llmModel"),
        "voiceStack": patch.get("voiceStack"),
        "geminiLiveVoiceName": patch.get("geminiLiveVoiceName"),
        "language": patch.get("language", "(left unchanged)"),
        "firstSpeaker": patch.get("firstSpeaker"),
        "silenceTimeoutSeconds": patch.get("silenceTimeoutSeconds"),
        "maxDuration": patch.get("maxDuration"),
        "recordingEnabled": patch.get("recordingEnabled"),
        "tools": [f"{t.get('type')}:{t.get('name')}" for t in patch.get("tools", [])],
        "dispositionSchema": [f["key"] for f in patch.get("dispositionSchema", [])],
    }


# --------------------------------------------------------------------------
# push
# --------------------------------------------------------------------------
async def push_to_snapserve(dry_run: bool = True) -> dict[str, Any]:
    """Render the prompt and (unless ``dry_run``) apply it to the live agent.

    Dry runs write ``backend/data/rendered_prompt.md`` and
    ``backend/data/agent_patch.json`` and touch nothing remote.
    """
    from services.snapserve import SnapServeError, get_client

    system_prompt = render_system_prompt()
    client = get_client()
    agent_id = settings.snapserve_agent_id

    current: Optional[dict] = None
    fetch_error: Optional[str] = None
    if client.configured:
        try:
            current = await client.get_agent(agent_id)
        except SnapServeError as exc:
            fetch_error = str(exc)
            logger.warning("could not fetch agent %s: %s", agent_id, fetch_error[:200])
    else:
        fetch_error = "SNAPSERVE_API_KEY not set"

    patch = build_agent_patch(system_prompt, current)

    prompt_path = settings.data_dir / "rendered_prompt.md"
    patch_path = settings.data_dir / "agent_patch.json"
    prompt_path.write_text(system_prompt, encoding="utf-8")
    patch_path.write_text(json.dumps(patch, indent=2, ensure_ascii=False), encoding="utf-8")

    result: dict[str, Any] = {
        "dry_run": dry_run,
        "agent_id": agent_id,
        "agent_name": (current or {}).get("name"),
        "prompt_path": str(prompt_path),
        "patch_path": str(patch_path),
        "approx_tokens": approx_tokens(system_prompt),
        "summary": patch_summary(patch),
        "fetch_error": fetch_error,
        "pushed": False,
    }

    if dry_run:
        logger.info("dry run: agent patch written to %s", patch_path)
        return result

    updated = await client.update_agent(agent_id, patch)
    meta_set(AGENT_SYNCED_KEY, now_iso())
    result["pushed"] = True
    result["agent_name"] = updated.get("name")
    logger.info("agent %s synced", agent_id)
    return result


# --------------------------------------------------------------------------
# status
# --------------------------------------------------------------------------
def knowledge_status() -> KnowledgeStatus:
    snapshot = providers.load_snapshot()
    prompt = render_system_prompt()

    sources: list[Citation] = []
    districts = days = notable = 0
    if snapshot is not None:
        districts = len(snapshot.districts)
        days = snapshot.days
        notable = sum(len(d.notable) for d in snapshot.districts) + len(snapshot.disasters)
        sources.extend(snapshot.citations)

    for fact in providers.load_facts():
        citation = fact.get("citation") if isinstance(fact, dict) else None
        if isinstance(citation, dict) and citation.get("id"):
            try:
                sources.append(Citation.model_validate(citation))
            except Exception:  # pragma: no cover - malformed sibling data
                continue

    seen: set[str] = set()
    unique: list[Citation] = []
    for citation in sources:
        if citation.id in seen:
            continue
        seen.add(citation.id)
        unique.append(citation)

    last_refresh = meta_get(LAST_REFRESH_KEY)
    if last_refresh is None and snapshot is not None and snapshot.generated_at:
        last_refresh = snapshot.generated_at

    return KnowledgeStatus(
        last_refresh_at=last_refresh,
        agent_synced_at=meta_get(AGENT_SYNCED_KEY),
        districts=districts,
        days=days,
        notable_events=notable,
        approx_tokens=approx_tokens(prompt),
        sources=unique,
    )


def mark_refreshed() -> None:
    meta_set(LAST_REFRESH_KEY, now_iso())
