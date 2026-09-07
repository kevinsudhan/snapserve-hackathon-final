"""The real snapshot on disk, the renders built from it, and the CLI builder."""

from __future__ import annotations

from datetime import date

import pytest

from services import knowledge_weather as kw
from services.crops import render_crop_calendar
from services.weather import check_weather, weather_citation

MAX_WEATHER_TOKENS = 15_000
MAX_CROP_TOKENS = 2_000


@pytest.fixture(scope="module")
def snapshot():
    try:
        return kw.load_snapshot()
    except FileNotFoundError:  # pragma: no cover - guarded so CI states the cause
        pytest.skip("weather_snapshot.json has not been built yet")


# --------------------------------------------------------------------------- #
# snapshot integrity
# --------------------------------------------------------------------------- #
def test_snapshot_covers_all_38_districts(snapshot):
    assert len(snapshot.districts) == 38
    assert len({d.name for d in snapshot.districts}) == 38


def test_every_district_has_a_full_series_and_a_real_request_url(snapshot):
    for district in snapshot.districts:
        assert len(district.daily) == snapshot.days, district.name
        assert district.source_url.startswith("https://api.open-meteo.com/v1/forecast?")
        assert f"latitude={district.lat}" in district.source_url
        assert district.daily[0].date == snapshot.coverage.start
        assert district.daily[-1].date == snapshot.coverage.end


def test_coverage_ends_before_today(snapshot):
    assert date.fromisoformat(snapshot.coverage.end) < date.today()
    assert snapshot.coverage.start < snapshot.coverage.end


def test_notable_days_match_the_documented_thresholds(snapshot):
    for district in snapshot.districts:
        by_date = {d.date: d for d in district.daily}
        for iso in district.notable:
            day = by_date[iso]
            assert (
                day.precipitation_mm >= kw.NOTABLE_RAIN_MM
                or day.wind_gust_kmh >= kw.NOTABLE_GUST_KMH
            )
        quiet = [
            d
            for d in district.daily
            if d.date not in set(district.notable)
            and (
                d.precipitation_mm >= kw.NOTABLE_RAIN_MM
                or d.wind_gust_kmh >= kw.NOTABLE_GUST_KMH
            )
        ]
        assert not quiet, f"{district.name} has unlisted notable days: {quiet}"


def test_every_district_has_a_citation_with_its_request_url(snapshot):
    by_id = {c.id: c for c in snapshot.citations}
    assert "W-open-meteo-docs" in by_id
    for district in snapshot.districts:
        citation = by_id[f"W-{kw.slugify_district(district.name)}"]
        assert citation.url == district.source_url
        assert citation.publisher == "Open-Meteo"
        assert citation.kind == "weather"


def test_disaster_events_have_report_urls_and_dates(snapshot):
    for event in snapshot.disasters:
        assert event.report_url.startswith("http")
        assert event.type in {"TC", "FL", "DR"}
        assert date.fromisoformat(event.from_) <= date.fromisoformat(event.to)


# --------------------------------------------------------------------------- #
# a real notable day
# --------------------------------------------------------------------------- #
def test_a_real_notable_day_reads_back_with_its_own_numbers(snapshot):
    """Pick the wettest day in the whole snapshot and re-check it end to end."""
    district, day = max(
        ((d, x) for d in snapshot.districts for x in d.daily),
        key=lambda pair: pair[1].precipitation_mm,
    )
    result = check_weather(district.lat, district.lon, day.date, "heavy_rain")
    assert result.source == "snapshot"
    assert result.metrics["district_used"] == district.name
    assert result.metrics["max_daily_rain_mm"] >= day.precipitation_mm
    assert result.request_url == district.source_url

    cid = f"W-{kw.slugify_district(district.name)}-{day.date}"
    citation = weather_citation(cid)
    assert citation is not None
    assert citation.id == cid
    assert f"{day.precipitation_mm} mm" in (citation.quote or "")


def test_a_named_notable_day_appears_in_the_render(snapshot):
    district = next(d for d in snapshot.districts if d.notable)
    iso = district.notable[0]
    day = next(x for x in district.daily if x.date == iso)
    text = kw.render_weather_knowledge(snapshot)
    marker = f"[W-{kw.slugify_district(district.name)}-{iso}]"
    assert marker in text
    line = next(ln for ln in text.splitlines() if marker in ln)
    assert f"{day.precipitation_mm:.1f}mm" in line


# --------------------------------------------------------------------------- #
# prompt renders
# --------------------------------------------------------------------------- #
def test_weather_render_is_inside_budget_and_states_the_rules(snapshot):
    text = kw.render_weather_knowledge(snapshot)
    assert kw.estimate_tokens(text) <= MAX_WEATHER_TOKENS
    assert f"Coverage: {snapshot.coverage.start} to {snapshot.coverage.end}" in text
    assert "you do NOT know" in text
    assert "under 10 mm rain and gusts under 45 km/h" in text
    for district in snapshot.districts:
        assert f"[W-{kw.slugify_district(district.name)}]" in text


def test_weather_render_has_weekly_lines_for_each_district(snapshot):
    text = kw.render_weather_knowledge(snapshot)
    weekly = [ln for ln in text.splitlines() if ln.startswith("  ") and "max gust" in ln]
    # 60 days -> 9 weekly buckets per district.
    assert len(weekly) == 9 * len(snapshot.districts)


def test_district_slugs_have_no_spaces(snapshot):
    for district in snapshot.districts:
        slug = kw.slugify_district(district.name)
        assert " " not in slug
    assert kw.slugify_district("The Nilgiris") == "TheNilgiris"
    assert kw.slugify_district("Tiruvannamalai") == "Tiruvannamalai"


def test_crop_render_is_inside_budget():
    text = render_crop_calendar()
    from services.knowledge_weather import estimate_tokens

    assert estimate_tokens(text) <= MAX_CROP_TOKENS
    assert "[C-" in text


def test_estimate_tokens_is_chars_over_four():
    assert kw.estimate_tokens("x" * 400) == 100


# --------------------------------------------------------------------------- #
# builder
# --------------------------------------------------------------------------- #
def test_data_down_build_writes_an_empty_snapshot(tmp_path, monkeypatch):
    monkeypatch.setattr(kw, "SNAPSHOT_PATH", tmp_path / "weather_snapshot.json")
    result = kw.build_weather_snapshot(60, data_down=True)
    assert result.districts == [] and result.coverage.start == ""
    assert (tmp_path / "weather_snapshot.json").exists()


@pytest.mark.network
def test_build_weather_snapshot_hits_the_real_apis(tmp_path, monkeypatch):
    """Opt-in: `pytest -m network`. Pulls a 3-day snapshot from Open-Meteo + GDACS."""
    monkeypatch.setattr(kw, "SNAPSHOT_PATH", tmp_path / "weather_snapshot.json")
    result = kw.build_weather_snapshot(3)
    assert len(result.districts) == 38
    assert all(len(d.daily) == 3 for d in result.districts)
    assert any(c.id == "W-open-meteo-docs" for c in result.citations)
