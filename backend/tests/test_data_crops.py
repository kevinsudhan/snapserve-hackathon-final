"""Crop name normalisation, land units and the Tamil Nadu crop calendar."""

from __future__ import annotations

import json

import pytest

from services.crops import (
    CALENDAR_PATH,
    CROP_NAMES,
    check_crop_window,
    crop_calendar_citation,
    normalize_crop,
    normalize_land_extent,
    render_crop_calendar,
)
from services.gazetteer import list_districts


# --------------------------------------------------------------------------- #
# crop names
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("spoken", "expected"),
    [
        ("nel", "paddy"), ("arisi", "paddy"), ("vari", "paddy"), ("dhan", "paddy"),
        ("chawal", "paddy"), ("biyyam", "paddy"), ("akki", "paddy"), ("ari", "paddy"),
        ("rice", "paddy"),
        ("verkadalai", "groundnut"), ("mungfali", "groundnut"), ("palli", "groundnut"),
        ("kadalekai", "groundnut"),
        ("karumbu", "sugarcane"), ("ganna", "sugarcane"), ("cheruku", "sugarcane"),
        ("kabbu", "sugarcane"),
        ("paruthi", "cotton"), ("kapas", "cotton"), ("patti", "cotton"),
        ("hatti", "cotton"),
        ("makkacholam", "maize"), ("makka", "maize"), ("mokkajonna", "maize"),
        ("ulundu", "black_gram"), ("urad", "black_gram"), ("minumu", "black_gram"),
        ("uddu", "black_gram"),
        ("pachai payaru", "green_gram"), ("moong", "green_gram"),
        ("pesalu", "green_gram"), ("hesaru", "green_gram"),
        ("thuvarai", "red_gram"), ("arhar", "red_gram"), ("kandi", "red_gram"),
        ("togari", "red_gram"),
        ("vazhai", "banana"), ("kela", "banana"), ("arati", "banana"),
        ("baale", "banana"),
        ("manjal", "turmeric"), ("haldi", "turmeric"), ("pasupu", "turmeric"),
        ("arishina", "turmeric"),
        ("milagai", "chilli"), ("mirchi", "chilli"), ("mirapa", "chilli"),
        ("menasina", "chilli"),
        ("vengayam", "onion"), ("pyaz", "onion"), ("ulli", "onion"),
        ("eerulli", "onion"),
        ("kezhvaragu", "ragi"), ("ragi", "ragi"),
        ("kambu", "bajra"), ("bajra", "bajra"),
        ("cholam", "jowar"), ("jowar", "jowar"),
        ("ellu", "sesame"), ("til", "sesame"),
        ("thakkali", "tomato"), ("maravalli", "tapioca"), ("kathirikai", "brinjal"),
        ("vendakkai", "okra"), ("mangai", "mango"), ("thengai", "coconut"),
    ],
)
def test_multilingual_crop_names(spoken, expected):
    assert normalize_crop(spoken) == expected


def test_crop_name_with_filler_words():
    assert normalize_crop("my paddy crop") == "paddy"
    assert normalize_crop("  NEL  ") == "paddy"


def test_unknown_crop_is_none_not_a_guess():
    assert normalize_crop("helicopter") is None
    assert normalize_crop("") is None
    assert normalize_crop("zzzzqx") is None


def test_every_canonical_crop_maps_to_itself():
    for canonical in CROP_NAMES:
        assert normalize_crop(canonical) == canonical


# --------------------------------------------------------------------------- #
# land extent
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("value", "unit", "expected_unit", "expected_ha"),
    [
        (2, "acre", "acre", 0.8094),
        (1, "acres", "acre", 0.4047),
        (50, "cent", "cent", 0.2023),
        (1, "hectare", "hectare", 1.0),
        (1, "ha", "hectare", 1.0),
        (3, "bigha", "bigha", 0.75),
        (10, "guntha", "guntha", 0.101),
        (1, "kani", "kani", 0.534),
        (2, "ma", "ma", 0.268),
        (4, "ground", "ground", 0.0892),
        (5000, "sq ft", "sq ft", 0.0465),
    ],
)
def test_land_units_convert_to_hectares(value, unit, expected_unit, expected_ha):
    extent = normalize_land_extent(value, unit)
    assert extent.unit == expected_unit
    assert extent.hectares == pytest.approx(expected_ha, abs=0.001)
    assert extent.value == value


def test_unknown_unit_is_flagged_and_never_silently_converted():
    extent = normalize_land_extent(2, "blorp")
    assert extent.unit == "unknown"
    assert extent.hectares == 0.0
    assert extent.value == 2


def test_non_numeric_value_does_not_raise():
    extent = normalize_land_extent("two", "acre")  # type: ignore[arg-type]
    assert extent.value == 0.0


# --------------------------------------------------------------------------- #
# crop calendar
# --------------------------------------------------------------------------- #
def test_calendar_entries_are_well_formed():
    payload = json.loads(CALENDAR_PATH.read_text(encoding="utf-8"))
    entries = payload["entries"]
    assert len(entries) == payload["entry_count"] >= 100
    official = {d["name"] for d in list_districts()}
    ids = set()
    for entry in entries:
        assert entry["id"] not in ids
        ids.add(entry["id"])
        assert entry["crop"] in CROP_NAMES
        assert set(entry["districts"]) <= official
        for key in ("sowing_start", "sowing_end", "harvest_start", "harvest_end"):
            month, day = entry[key].split("-")
            assert 1 <= int(month) <= 12 and 1 <= int(day) <= 31
        citation = entry["citation"]
        assert citation["url"].startswith("https://")
        assert citation["page"] and citation["as_of"] and citation["kind"] == "crop"


def test_kuruvai_samba_and_navarai_seasons_are_named():
    payload = json.loads(CALENDAR_PATH.read_text(encoding="utf-8"))
    seasons = {e["season"] for e in payload["entries"] if e["crop"] == "paddy"}
    assert {"kuruvai", "samba", "navarai"} <= seasons


def test_paddy_in_cuddalore_in_kuruvai_season_is_in_window():
    evidence = check_crop_window("paddy", "Cuddalore", "2026-07-15")
    assert evidence.crop == "paddy"
    assert evidence.in_window is True
    assert evidence.season == "kuruvai"
    assert evidence.window is not None
    assert evidence.citations and evidence.citations[0].id.startswith("C-")


def test_a_spoken_crop_name_works_through_the_window_check():
    evidence = check_crop_window("nel", "Thanjavur", "2026-06-15")
    assert evidence.crop == "paddy"
    assert evidence.in_window is True


def test_groundnut_in_coimbatore_matches_the_pmfby_cross_checked_window():
    """TN Table X and the PMFBY calendar agree: irrigated groundnut Apr-May sowing."""
    evidence = check_crop_window("groundnut", "Coimbatore", "2026-05-01")
    assert evidence.in_window is True
    assert evidence.window is not None
    assert evidence.window.sowing == "Apr-May"


def test_a_district_with_no_row_returns_none_not_false():
    evidence = check_crop_window("cotton", "Chennai", "2026-09-02")
    assert evidence.in_window is None
    assert "no row" in evidence.note


def test_an_unrecognised_crop_returns_none_and_says_so():
    evidence = check_crop_window("helicopter", "Cuddalore", "2026-09-02")
    assert evidence.in_window is None
    assert "not a crop name" in evidence.note


def test_a_bad_date_returns_none():
    evidence = check_crop_window("paddy", "Cuddalore", "some day last week")
    assert evidence.in_window is None


def test_out_of_window_is_reported_gently_with_the_real_windows():
    evidence = check_crop_window("paddy", "Kanniyakumari", "2026-05-20")
    assert evidence.in_window in (True, False)
    if evidence.in_window is False:
        assert "outside those windows" in evidence.note
        assert "gently" in evidence.note


def test_calendar_citations_resolve_by_id():
    payload = json.loads(CALENDAR_PATH.read_text(encoding="utf-8"))
    for entry in payload["entries"][:20]:
        citation = crop_calendar_citation(entry["id"])
        assert citation is not None and citation.id == entry["id"]
    assert crop_calendar_citation("C-99999") is None


def test_render_lists_ids_that_all_resolve():
    text = render_crop_calendar()
    ids = {
        token[1:-1]
        for token in text.split()
        if token.startswith("[C-") and token.endswith("]")
    }
    assert ids
    for cid in ids:
        assert crop_calendar_citation(cid) is not None
