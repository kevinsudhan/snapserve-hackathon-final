"""Tests for the scheme knowledge layer.

The important ones are not unit tests of Python logic — they are checks that the
data the voice agent is allowed to speak is real: every fact has a URL, a page
or section, a retrieval date and a quote, and every quote from a source we hold
locally is genuinely verbatim in that source.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from services import schemes
from services.schemes_models import Citation, EvidenceItem, SchemeMatch

BACKEND_DIR = Path(__file__).resolve().parent.parent
SOURCES_DIR = BACKEND_DIR / "data" / "sources"


# ---------------------------------------------------------------------------
# Fact integrity
# ---------------------------------------------------------------------------

def test_facts_load():
    facts = schemes.load_facts()
    assert len(facts) >= 40, "not enough scheme facts to be useful"
    ids = [f["id"] for f in facts]
    assert len(ids) == len(set(ids)), "duplicate fact ids"
    assert all(re.fullmatch(r"S\d+", i) for i in ids), "fact ids must look like S12"


@pytest.mark.parametrize("fact", schemes.load_facts(), ids=lambda f: f["id"])
def test_every_fact_has_a_real_citation(fact):
    """No fact without url + page (or section) + quote + as_of. Non-negotiable."""
    citation = fact["citation"]
    assert citation["id"] == fact["id"], "citation id must equal fact id"
    assert citation["url"].startswith("http"), "citation needs a real URL"
    assert citation.get("page"), "citation needs a page or section reference"
    assert citation.get("quote"), "citation needs a verbatim quote"
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", citation["as_of"]), "as_of must be a date"
    assert citation.get("title") and citation.get("publisher")
    assert citation["kind"] == "scheme"
    assert len(citation["quote"].split()) <= 25, "quote must stay under 25 words"

    assert fact["text"].strip().endswith("."), "fact text must be a full sentence"
    assert fact["sensitivity"] in ("normal", "never_promise")
    assert isinstance(fact["applies_to"], dict)
    # Model round-trip: core imports these types.
    Citation(**citation)


def _normalise(text: str) -> str:
    """Collapse a string to letters and digits so PDF extraction artefacts
    (stray spaces, hyphenation, curly quotes) do not cause false failures."""
    for src, dst in (("‘", "'"), ("’", "'"), ("“", '"'),
                     ("”", '"'), ("‟", '"'), ("–", "-"),
                     ("—", "-")):
        text = text.replace(src, dst)
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _local_corpora() -> dict[str, str]:
    """URL fragment -> normalised full text of the local copy of that source."""
    pytest.importorskip("pypdf")
    from pypdf import PdfReader

    corpora: dict[str, str] = {}

    for fragment, filename in (
        ("pmfby.gov.in/pdf/Revamped", "PMFBY_Revamped_OGs_Final.pdf"),
        ("RWBCIS_Revised", "RWBCIS_Revised_Guidelines.pdf"),
    ):
        path = SOURCES_DIR / filename
        if path.exists():
            reader = PdfReader(str(path))
            corpora[fragment] = _normalise(
                " ".join((page.extract_text() or "") for page in reader.pages)
            )

    for fragment, filename in (
        ("pib.gov.in", "pib_pmfby_og_2197713.html"),
        ("businessminutes.in", "tn_kharif2026_hdfcergo_press.html"),
        ("des.tn.gov.in", "des_tn_pmfby.html"),
    ):
        path = SOURCES_DIR / filename
        if path.exists():
            raw = path.read_text(encoding="utf-8", errors="replace")
            raw = re.sub(r"<script.*?</script>", " ", raw, flags=re.S | re.I)
            raw = re.sub(r"<style.*?</style>", " ", raw, flags=re.S | re.I)
            raw = re.sub(r"<[^>]+>", " ", raw)
            raw = raw.replace("&amp;", "&").replace("&nbsp;", " ")
            corpora[fragment] = _normalise(raw)

    return corpora


def test_every_quote_is_verbatim_in_its_source():
    """Re-extract the downloaded sources and prove each quote is really there."""
    corpora = _local_corpora()
    if not corpora:
        pytest.skip("no local source copies in backend/data/sources")

    checked = 0
    failures = []
    for fact in schemes.load_facts():
        citation = fact["citation"]
        key = next((k for k in corpora if k in citation["url"]), None)
        if key is None:
            continue
        checked += 1
        if _normalise(citation["quote"]) not in corpora[key]:
            failures.append(f"{fact['id']}: {citation['quote'][:80]!r}")

    assert not failures, "quotes not found verbatim in source:\n" + "\n".join(failures)
    assert checked >= 40, "expected most facts to be checkable against a local source"


def test_pmfby_core_topics_are_covered():
    fields = {f["field"] for f in schemes.load_facts()}
    for required in (
        "purpose", "who_can_enrol", "crops_covered", "risks_covered",
        "exclusions", "intimation", "premium", "assessment", "documents",
        "grievance", "helpline", "claim_timeline", "state_notification",
    ):
        assert required in fields, f"no fact covers {required}"


def test_timeline_facts_are_marked_never_promise():
    for fact in schemes.load_facts():
        if fact["field"] in ("claim_timeline", "claim_payment"):
            assert fact["sensitivity"] == "never_promise", fact["id"]


# ---------------------------------------------------------------------------
# lookup_scheme
# ---------------------------------------------------------------------------

def test_lookup_paddy_cuddalore_cyclone():
    matches, unknowns = schemes.lookup_scheme(
        crop="paddy", district="Cuddalore", event_date="2026-09-12",
        damage_type="cyclone",
    )
    assert matches, "no scheme facts matched a paddy cyclone claim in Cuddalore"
    assert all(isinstance(m, SchemeMatch) for m in matches)

    texts = " ".join(m.text.lower() for m in matches)
    ids = {m.fact_id for m in matches}

    # The seventy-two hour intimation rule must be there.
    assert "seventy-two hours" in texts, "the 72-hour intimation fact is missing"
    assert "S34" in ids

    # Cyclone as a standing-crop risk, and the post-harvest cover.
    assert "cyclone" in texts
    assert any("post-harvest" in m.text.lower() or "post harvest" in m.text.lower()
               for m in matches), "post-harvest coverage is missing"
    assert "S23" in ids and "S24" in ids

    # Tamil Nadu / Cuddalore notification facts should surface, including which
    # company runs the scheme there this season.
    assert any(m.field == "state_notification" for m in matches)
    assert "S77" in ids and "S78" in ids

    # The pinned facts a reviewer always wants: what the scheme is, what is
    # never covered, and the government helpline.
    assert {"S1", "S31", "S71"} <= ids

    # The list is capped so a claim record stays readable.
    assert len(matches) < len(schemes.load_facts())

    # Every match still carries its citation.
    for match in matches:
        assert match.citation.url.startswith("http")
        assert match.citation.quote

    assert unknowns, "lookup must always say what it does not know"
    assert all(u.strip().endswith(".") for u in unknowns), "unknowns must be sentences"
    joined = " ".join(unknowns).lower()
    assert "sum insured" in joined
    assert "reviewer" in joined


def test_lookup_excludes_facts_for_other_events():
    matches, _ = schemes.lookup_scheme(
        crop="paddy", district="Cuddalore", event_date="2026-09-12",
        damage_type="cyclone",
    )
    ids = {m.fact_id for m in matches}
    # S75 is the prevented-sowing threshold; it has nothing to do with a cyclone.
    assert "S75" not in ids


def test_lookup_with_nothing_known_still_returns_general_facts_and_unknowns():
    matches, unknowns = schemes.lookup_scheme(None, None, None, None)
    assert matches, "general scheme facts should always be available"
    assert all(not (m.citation.page is None) for m in matches)
    assert len(unknowns) >= 4


def test_lookup_outside_tamil_nadu_says_so():
    _, unknowns = schemes.lookup_scheme(
        crop="wheat", district="Ludhiana", event_date="2026-01-10",
        damage_type="hailstorm",
    )
    joined = " ".join(unknowns).lower()
    assert "reviewer" in joined


def test_season_derivation():
    assert schemes.season_for_date("2026-09-12") == "kharif"
    assert schemes.season_for_date("2026-12-20") == "rabi"
    assert schemes.season_for_date(None) is None


# ---------------------------------------------------------------------------
# Evidence
# ---------------------------------------------------------------------------

def test_evidence_checklist_for_cyclone():
    items = schemes.evidence_checklist("cyclone", "paddy")
    assert all(isinstance(i, EvidenceItem) for i in items)
    keys = {i.key for i in items}
    assert "damaged_crop_photos" in keys, "photos of the damage are always needed"
    assert "land_record" in keys, "the land record is always needed"
    assert "sowing_certificate" in keys
    assert "bank_passbook" in keys
    assert "aadhaar" in keys
    assert "premium_receipt" in keys
    # Cyclone is also a post-harvest peril, so offer the cut-crop photo.
    assert "cut_crop_photo" in keys

    for item in items:
        assert item.why.strip(), f"{item.key} has no reason to give the farmer"
        assert item.citation_id, f"{item.key} is not tied to a scheme fact"
        assert schemes.citation_by_id(item.citation_id) is not None, item.citation_id


def test_evidence_checklist_pest_adds_a_closeup():
    keys = {i.key for i in schemes.evidence_checklist("pest", "paddy")}
    assert "closeup_pest_photo" in keys


def test_evidence_checklist_post_harvest_asks_for_the_cut_crop():
    keys = {i.key for i in schemes.evidence_checklist("post_harvest", "paddy")}
    assert "cut_crop_photo" in keys


def test_evidence_checklist_has_no_duplicate_keys():
    for damage in (None, "cyclone", "hailstorm", "pest", "post_harvest", "flood"):
        items = schemes.evidence_checklist(damage, "paddy")
        keys = [i.key for i in items]
        assert len(keys) == len(set(keys)), damage


# ---------------------------------------------------------------------------
# Safe scripts
# ---------------------------------------------------------------------------

BANNED_SUBSTRINGS = [
    "approv", "guarant", "within", "promis", "assur",
    "definitely", "surely", "certainly", "rupee", "lakh", "crore",
]


def _script_strings(node, path="") -> list[tuple[str, str]]:
    out = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "generated_at":
                continue
            out += _script_strings(value, f"{path}/{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            out += _script_strings(value, f"{path}[{index}]")
    else:
        out.append((path, str(node)))
    return out


def test_safe_scripts_have_the_contract_keys():
    scripts = schemes.safe_scripts()
    for key in ("payout_question", "approval_question", "timeline_question",
                "escalation", "data_unavailable"):
        assert key in scripts, key
    for key in ("payout_question", "approval_question", "timeline_question",
                "yes_or_no_demand"):
        assert scripts[key]["say"].strip()
        assert scripts[key]["if_caller_insists"].strip()


def test_safe_scripts_never_leak_an_outcome():
    for path, text in _script_strings(schemes.safe_scripts()):
        assert not re.search(r"\d", text), f"{path} contains a digit: {text[:60]}"
        assert not re.search(r"[₹$]", text), f"{path} contains a currency symbol"
        for banned in BANNED_SUBSTRINGS:
            assert banned not in text.lower(), f"{path} contains {banned!r}: {text[:60]}"


def test_escalation_scripts_cover_every_trigger():
    escalation = schemes.safe_scripts()["escalation"]
    for reason in ("weather_mismatch", "contradictory_details",
                   "unusually_large_area", "data_unavailable", "distress",
                   "asked_for_human"):
        assert reason in escalation, reason
        assert escalation[reason]["say"].strip()


def test_safe_scripts_say_what_happens_next():
    scripts = schemes.safe_scripts()
    for key in ("payout_question", "approval_question", "timeline_question",
                "yes_or_no_demand"):
        say = scripts[key]["say"].lower()
        assert "reviewer" in say or "person" in say, key


def test_contradiction_probes_exist():
    probes = schemes.safe_scripts()["contradiction_probes"]
    for key in ("date", "place", "crop", "area"):
        assert probes[key].strip()


# ---------------------------------------------------------------------------
# Rendering and citation resolution
# ---------------------------------------------------------------------------

def test_render_scheme_knowledge_uses_ids_and_flags_promises():
    text = schemes.render_scheme_knowledge()
    assert "[S1]" in text and "[S34]" in text
    for fact in schemes.load_facts():
        assert f"[{fact['id']}]" in text, fact["id"]
        if fact["sensitivity"] == "never_promise":
            line = next(l for l in text.splitlines() if l.startswith(f"[{fact['id']}]"))
            assert "NEVER PROMISE" in line, fact["id"]
    assert "never read an id out loud" in text


def test_render_blocks_are_non_empty():
    assert len(schemes.render_evidence_checklists()) > 500
    assert len(schemes.render_safe_scripts()) > 500


def test_citation_by_id():
    citation = schemes.citation_by_id("S34")
    assert citation is not None
    assert citation.url.startswith("https://pmfby.gov.in/")
    assert citation.kind == "scheme"
    # Ids owned by other modules, and nonsense ids, resolve to None here.
    assert schemes.citation_by_id("W-Cuddalore-2026-09-02") is None
    assert schemes.citation_by_id("C-3") is None
    assert schemes.citation_by_id("G-1") is None
    assert schemes.citation_by_id("S99999") is None
    assert schemes.citation_by_id("") is None


def test_system_prompt_has_every_placeholder():
    prompt = (BACKEND_DIR / "prompts" / "system_prompt.md").read_text(encoding="utf-8")
    for placeholder in ("SCHEME_KNOWLEDGE", "WEATHER_KNOWLEDGE", "CROP_CALENDAR",
                        "EVIDENCE_CHECKLISTS", "SAFE_SCRIPTS", "REVIEWER_PHONE",
                        "GENERATED_AT"):
        assert "{{" + placeholder + "}}" in prompt, placeholder
    body = re.sub(r"\{\{[A-Z_]+\}\}", "", prompt)
    assert len(body.split()) < 2500, "prompt is too long for a live voice agent"


def test_schemes_json_is_valid_utf8_json():
    raw = (BACKEND_DIR / "data" / "schemes.json").read_text(encoding="utf-8")
    doc = json.loads(raw)
    assert doc["facts"]
