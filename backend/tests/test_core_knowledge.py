"""Prompt rendering, placeholder substitution and the SnapServe agent patch."""

from __future__ import annotations

import json

from app.config import settings
from services import knowledge


def test_every_placeholder_is_filled():
    rendered = knowledge.render_system_prompt()
    assert rendered.strip()
    for name in knowledge.PLACEHOLDERS:
        assert "{{" + name + "}}" not in rendered, f"{name} was left unfilled"


def test_rendered_prompt_carries_the_injected_knowledge():
    rendered = knowledge.render_system_prompt()
    assert settings.reviewer_phone in rendered
    # GENERATED_AT renders as a weekday + IST timestamp
    assert "IST" in rendered
    assert any(
        day in rendered
        for day in ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
                    "Saturday", "Sunday")
    )


def test_approx_tokens_is_chars_over_four():
    assert knowledge.approx_tokens("x" * 400) == 100
    assert knowledge.approx_tokens("") == 0


def test_prompt_is_within_a_sane_size():
    tokens = knowledge.approx_tokens(knowledge.render_system_prompt())
    assert 200 < tokens < 200_000


def test_evidence_checklists_render_with_keys():
    block = knowledge.render_evidence_checklists()
    assert block.strip()
    assert "[" in block and "]" in block  # item keys are bracketed
    assert "required" in block


def test_safe_scripts_render_with_no_promise_guidance() -> None:
    block = knowledge.render_safe_scripts()
    assert block.strip()
    assert "caller's own language" in block
    assert "never add an amount" in block


# --------------------------------------------------------------------------
# agent patch
# --------------------------------------------------------------------------
def test_agent_patch_matches_the_contract():
    patch = knowledge.build_agent_patch("SYSTEM PROMPT BODY")

    assert patch["systemPrompt"] == "SYSTEM PROMPT BODY"
    assert patch["llmProvider"] == "google"
    assert patch["llmModel"] == settings.gemini_live_model
    assert patch["voiceStack"] == "gemini_live"
    assert patch["geminiLiveVoiceName"] == settings.gemini_live_voice_name
    assert patch["firstSpeaker"] == "assistant"
    assert patch["silenceTimeoutSeconds"] == 12
    assert patch["maxDuration"] == 900
    assert patch["recordingEnabled"] is True
    assert patch["inactivityMessage"]


def test_greeting_is_one_warm_sentence_inviting_any_language():
    greeting = knowledge.GREETING
    assert greeting.count(".") <= 1
    assert len(greeting) < 260
    assert "language" in greeting.lower()


def test_language_is_left_alone_unless_configured(monkeypatch):
    monkeypatch.setattr(settings, "agent_language", "")
    assert "language" not in knowledge.build_agent_patch("p")
    monkeypatch.setattr(settings, "agent_language", "en-IN")
    assert knowledge.build_agent_patch("p")["language"] == "en-IN"


def test_transfer_tool_targets_the_reviewer_with_a_warm_summary():
    patch = knowledge.build_agent_patch("p")
    transfer = next(t for t in patch["tools"] if t["type"] == "call_transfer")
    assert transfer["name"] == "transfer_to_reviewer"
    assert transfer["transferTo"] == settings.reviewer_phone
    assert transfer["transferMode"] == "warm_summary"
    assert transfer["warmHandoffMessage"]
    assert transfer["summaryPrompt"]


def test_existing_end_call_tool_is_kept_and_transfer_is_deduped():
    current = {
        "tools": [
            {"type": "end_call", "name": "end_call", "description": "hang up"},
            {"type": "call_transfer", "name": "old_transfer", "transferTo": "+910000000000"},
        ]
    }
    tools = knowledge.build_agent_patch("p", current)["tools"]
    kinds = [t["type"] for t in tools]
    assert kinds.count("end_call") == 1
    assert kinds.count("call_transfer") == 1
    assert not any(t.get("name") == "old_transfer" for t in tools)


def test_end_call_is_added_when_the_agent_has_none():
    tools = knowledge.build_agent_patch("p", {"tools": []})["tools"]
    assert any(t["type"] == "end_call" for t in tools)


def test_disposition_schema_captures_the_intake_fields():
    schema = knowledge.disposition_schema()
    keys = [field["key"] for field in schema]
    assert keys == ["crop", "land_extent", "damage_type", "event_date",
                    "village", "district", "outcome"]
    outcome = schema[-1]
    assert outcome["type"] == "choice"
    assert outcome["options"] == ["logged", "escalated", "incomplete"]
    assert outcome["required"] is True


def test_patch_summary_never_leaks_the_prompt_body():
    patch = knowledge.build_agent_patch("SECRET PROMPT " * 100)
    summary = knowledge.patch_summary(patch)
    assert "SECRET PROMPT" not in json.dumps(summary)
    assert summary["systemPrompt_chars"] > 0
    assert summary["systemPrompt_approx_tokens"] > 0


# --------------------------------------------------------------------------
# dry run
# --------------------------------------------------------------------------
def test_dry_run_writes_files_and_pushes_nothing(monkeypatch, tmp_path):
    import asyncio

    from services import snapserve

    monkeypatch.setattr(settings, "data_dir", tmp_path)

    def refuse(*_args, **_kwargs):
        raise AssertionError("a dry run must not call the SnapServe API")

    async def fake_get_agent(self, agent_id):  # noqa: ANN001, ARG001
        return {"name": "Sunil", "tools": []}

    monkeypatch.setattr(snapserve.SnapServeClient, "update_agent", refuse)
    monkeypatch.setattr(snapserve.SnapServeClient, "get_agent", fake_get_agent)

    result = asyncio.run(knowledge.push_to_snapserve(dry_run=True))

    assert result["dry_run"] is True
    assert result["pushed"] is False
    assert (tmp_path / "rendered_prompt.md").exists()
    written = json.loads((tmp_path / "agent_patch.json").read_text(encoding="utf-8"))
    assert written["llmModel"] == settings.gemini_live_model
    assert written["voiceStack"] == "gemini_live"


# --------------------------------------------------------------------------
# status
# --------------------------------------------------------------------------
def test_knowledge_status_shape(clean_db):
    status = knowledge.knowledge_status()
    assert status.approx_tokens > 0
    assert status.districts >= 0
    assert isinstance(status.sources, list)
