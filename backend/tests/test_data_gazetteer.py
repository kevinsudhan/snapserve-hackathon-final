"""Offline location resolution: districts, aliases, towns and unknown places."""

from __future__ import annotations

import pytest

from services.gazetteer import (
    DISTRICT_ALIASES,
    TOWN_TO_DISTRICT,
    district_slug,
    gazetteer_citation,
    list_districts,
    resolve_location,
)


def test_all_38_districts_have_coordinates_inside_tamil_nadu():
    districts = list_districts()
    assert len(districts) == 38
    for district in districts:
        assert 8.0 <= district["lat"] <= 13.6, district
        assert 76.2 <= district["lon"] <= 80.4, district


def test_the_districts_created_after_2019_are_present():
    names = {d["name"] for d in list_districts()}
    for name in [
        "Tenkasi", "Kallakurichi", "Chengalpattu", "Ranipet",
        "Tirupathur", "Mayiladuthurai",
    ]:
        assert name in names


@pytest.mark.parametrize(
    ("spoken", "expected"),
    [
        ("Kovai", "Coimbatore"),
        ("Trichy", "Tiruchirappalli"),
        ("Tuticorin", "Thoothukudi"),
        ("Nagai", "Nagapattinam"),
        ("Kanyakumari", "Kanniyakumari"),
        ("Thanjai", "Thanjavur"),
        ("Nellai", "Tirunelveli"),
        ("Mathurai", "Madurai"),
        ("Velur", "Vellore"),
        ("Kadalur", "Cuddalore"),
        ("Villupuram", "Viluppuram"),
        ("Ooty", "The Nilgiris"),
        ("Pudukottai", "Pudukkottai"),
        ("Sivagangai", "Sivaganga"),
        ("Virudunagar", "Virudhunagar"),
        ("Ramnad", "Ramanathapuram"),
        ("Madras", "Chennai"),
        ("Kanchipuram", "Kancheepuram"),
        ("Tirupattur", "Tirupathur"),
        ("Cuddalore district", "Cuddalore"),
    ],
)
def test_district_aliases_resolve(spoken, expected):
    location = resolve_location(None, None, spoken)
    assert location.district == expected
    assert location.resolution_confidence == 0.9
    assert location.resolved_by == "district"
    assert location.lat is not None and location.lon is not None
    assert location.citation_id == f"G-{district_slug(expected)}"


def test_every_alias_points_at_a_real_district():
    names = {d["name"] for d in list_districts()}
    assert set(DISTRICT_ALIASES.values()) <= names
    assert set(TOWN_TO_DISTRICT.values()) <= names


def test_town_table_is_large_enough_to_be_useful():
    assert len(TOWN_TO_DISTRICT) >= 150


@pytest.mark.parametrize(
    ("taluk", "expected"),
    [
        ("Chidambaram", "Cuddalore"),
        ("Sivakasi", "Virudhunagar"),
        ("Kumbakonam", "Thanjavur"),
        ("Hosur", "Krishnagiri"),
        ("Karaikudi", "Sivaganga"),
        ("Mannargudi", "Tiruvarur"),
        ("Palani", "Dindigul"),
        ("Gobichettipalayam", "Erode"),
    ],
)
def test_taluks_resolve_to_their_district_at_lower_confidence(taluk, expected):
    location = resolve_location(None, taluk, None)
    assert location.district == expected
    assert location.resolution_confidence == 0.8
    assert location.resolved_by == "taluk"


def test_a_well_known_town_given_as_a_village_still_resolves():
    location = resolve_location("Velankanni", None, None)
    assert location.district == "Nagapattinam"
    assert location.resolution_confidence == 0.8
    assert location.resolved_by == "town"


def test_district_wins_over_a_taluk_that_disagrees():
    location = resolve_location(None, "Chidambaram", "Madurai")
    assert location.district == "Madurai"
    assert location.resolved_by == "district"


def test_unknown_village_keeps_the_name_but_invents_no_coordinates():
    location = resolve_location("Somerandompatti", None, None)
    assert location.district is None
    assert location.lat is None and location.lon is None
    assert location.resolution_confidence == 0.5
    assert location.resolved_by == "unresolved_village"


def test_nothing_given_resolves_to_nothing():
    location = resolve_location(None, None, None)
    assert location.resolution_confidence == 0.0
    assert location.lat is None and location.lon is None


def test_a_place_outside_tamil_nadu_is_not_resolved():
    location = resolve_location(None, None, "Kolar", state="Karnataka")
    assert location.resolution_confidence == 0.0
    assert location.resolved_by == "outside_tamil_nadu"
    assert location.lat is None


def test_gazetteer_citations_resolve_for_every_district():
    for district in list_districts():
        cid = f"G-{district_slug(district['name'])}"
        citation = gazetteer_citation(cid)
        assert citation is not None and citation.id == cid
        assert citation.url.startswith("https://www.tn.gov.in/")
        assert citation.kind == "gazetteer"
        assert str(district["lat"]) in (citation.quote or "")


def test_unknown_citation_id_returns_none():
    assert gazetteer_citation("G-atlantis") is None
    assert gazetteer_citation("S12") is None


def test_district_slug_shape():
    assert district_slug("The Nilgiris") == "the-nilgiris"
    assert district_slug("Tiruvannamalai") == "tiruvannamalai"
