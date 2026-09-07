"""Transcript parsing, language detection and the deterministic extractor."""

from __future__ import annotations

from datetime import date

import pytest

from services import ingest


# --------------------------------------------------------------------------
# parsing
# --------------------------------------------------------------------------
def test_parses_agent_and_caller_turns():
    turns = ingest.parse_transcript(
        "Agent: Hello, how can I help?\n"
        "Caller: My paddy crop is damaged.\n"
        "Agent: I am sorry to hear that."
    )
    assert [t.role for t in turns] == ["agent", "caller", "agent"]
    assert [t.i for t in turns] == [0, 1, 2]
    assert turns[1].text == "My paddy crop is damaged."


def test_parses_alternative_labels_and_missing_space_after_colon():
    turns = ingest.parse_transcript(
        "Assistant:Good morning\n"
        "User:Naan Cuddalore-la irukken\n"
        "Bot: Thank you\n"
        "Farmer: Nel payir"
    )
    assert [t.role for t in turns] == ["agent", "caller", "agent", "caller"]
    assert turns[0].text == "Good morning"


def test_unlabelled_line_continues_the_previous_speaker():
    turns = ingest.parse_transcript(
        "Caller: The rain started on Tuesday\nand it did not stop for two days\nAgent: I see."
    )
    assert len(turns) == 2
    assert "did not stop for two days" in turns[0].text
    assert turns[0].role == "caller"


def test_blank_lines_and_empty_transcript_are_safe():
    assert ingest.parse_transcript("") == []
    assert ingest.parse_transcript(None) == []
    turns = ingest.parse_transcript("Agent: Hi\n\n\nCaller: Hello\n")
    assert len(turns) == 2


def test_stt_dropped_spaces_do_not_break_extraction():
    """The STT glues words together — "thisis Priyafrom Cuddalore"."""
    turns = ingest.parse_transcript(
        "Agent: Please tell me your name and village.\n"
        "Caller: Sir thisis Priyafrom Cuddalore mypaddy in twoacres isdamaged"
    )
    assert len(turns) == 2
    extraction = ingest.heuristic_extract(turns, date(2026, 9, 5))
    assert extraction.farmer_name == "Priya"
    assert extraction.district == "Cuddalore"
    assert extraction.crop == "paddy"
    assert extraction.land_extent_value == 2
    assert extraction.land_extent_unit.startswith("acre")


def test_name_cleaner_strips_glued_words():
    assert ingest.find_name("thisis Rajafrom Salem") == "Raja"
    assert ingest.find_name("my name is Murugan") == "Murugan"
    assert ingest.find_name("no name here") is None


# --------------------------------------------------------------------------
# language detection
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "text,expected",
    [
        ("என் நெல் பயிர் மழையில் சேதம் அடைந்தது இது மிகவும் கஷ்டம்", "ta"),
        ("मेरी धान की फसल बारिश में बर्बाद हो गई है साहब", "hi"),
        ("నా వరి పంట వర్షంలో పాడైపోయింది సార్ చాలా నష్టం", "te"),
        ("ನನ್ನ ಭತ್ತದ ಬೆಳೆ ಮಳೆಯಲ್ಲಿ ಹಾಳಾಗಿದೆ ಸರ್", "kn"),
        ("എന്റെ നെല്ല് കൃഷി മഴയിൽ നശിച്ചു സാർ", "ml"),
    ],
)
def test_detects_native_scripts(text, expected):
    turns = ingest.parse_transcript(f"Caller: {text}")
    language, languages, _ = ingest.detect_languages(turns)
    assert language == expected
    assert expected in languages


def test_detects_code_switching():
    turns = ingest.parse_transcript(
        "Caller: Sir என் நெல் பயிர் damage ஆகிடுச்சு, insurance claim பண்ணனும், "
        "please help me with the process today"
    )
    _, languages, code_switching = ingest.detect_languages(turns)
    assert code_switching is True
    assert "ta" in languages


def test_english_only_is_not_code_switching():
    turns = ingest.parse_transcript(
        "Caller: My paddy crop in Cuddalore district was damaged by heavy rain last week."
    )
    language, _, code_switching = ingest.detect_languages(turns)
    assert language == "en"
    assert code_switching is False


# --------------------------------------------------------------------------
# dates and extents
# --------------------------------------------------------------------------
CALL_DATE = date(2026, 9, 5)


@pytest.mark.parametrize(
    "text,expected,min_confidence",
    [
        ("it happened on 12 August", "2026-08-12", 0.8),
        ("the damage was on August 12", "2026-08-12", 0.8),
        ("on 12September the storm came", "2025-09-12", 0.8),
        ("it was 02/09/2026", "2026-09-02", 0.8),
        ("three days ago", "2026-09-02", 0.5),
        ("two weeks back", "2026-08-22", 0.5),
        ("yesterday the water came", "2026-09-04", 0.6),
        ("day before yesterday", "2026-09-03", 0.6),
        ("last Tuesday", "2026-09-01", 0.4),
        ("last week", "2026-08-29", 0.3),
    ],
)
def test_resolves_relative_and_absolute_dates(text, expected, min_confidence):
    resolved, confidence = ingest.resolve_date_phrase(text, CALL_DATE)
    assert resolved == expected
    assert confidence >= min_confidence


def test_future_date_rolls_back_a_year():
    """A date after the call date must belong to the previous year."""
    resolved, _ = ingest.resolve_date_phrase("on 20 December", CALL_DATE)
    assert resolved == "2025-12-20"


def test_no_date_mentioned():
    resolved, confidence = ingest.resolve_date_phrase("my crop is gone", CALL_DATE)
    assert resolved is None
    assert confidence == 0.0


@pytest.mark.parametrize(
    "text,value,unit",
    [
        ("I have two acres of paddy", 2.0, "acre"),
        ("threeacres damaged", 3.0, "acre"),
        ("1.5 hectares", 1.5, "hectare"),
        ("50 cents of land", 50.0, "cent"),
    ],
)
def test_finds_land_extents(text, value, unit):
    extents = ingest.find_extents(text)
    assert extents
    assert extents[0][0] == value
    assert extents[0][1].startswith(unit[:4])


def test_contradictory_dates_and_extents_are_flagged():
    turns = ingest.parse_transcript(
        "Caller: The flood was on 12 August and I lost two acres.\n"
        "Agent: Can you confirm the date?\n"
        "Caller: Actually it was 20 August, and it is five acres."
    )
    extraction = ingest.heuristic_extract(turns, CALL_DATE)
    assert len(extraction.contradictions) >= 2
    joined = " ".join(extraction.contradictions).lower()
    assert "date" in joined
    assert "extent" in joined


def test_distress_and_human_request_are_detected():
    turns = ingest.parse_transcript(
        "Caller: Please help me, I have nothing to eat. "
        "I want to talk to a person, not a machine."
    )
    extraction = ingest.heuristic_extract(turns, CALL_DATE)
    assert extraction.distress is True
    assert extraction.asked_for_human is True


def test_outcome_questions_are_captured():
    turns = ingest.parse_transcript(
        "Caller: How much money will I get? When will it come to my account?"
    )
    extraction = ingest.heuristic_extract(turns, CALL_DATE)
    assert len(extraction.outcome_questions_asked) >= 1
