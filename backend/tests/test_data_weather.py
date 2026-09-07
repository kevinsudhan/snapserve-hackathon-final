"""Threshold logic and coverage handling for services.weather."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from services import weather
from services.models import (
    Citation,
    SnapshotDistrict,
    WeatherDay,
    WeatherSnapshot,
    WeatherWindow,
)

START = date(2026, 7, 7)
END = date(2026, 9, 4)
EVENT = "2026-08-15"
LAT, LON = 11.748, 79.7714  # Cuddalore centroid


def _snapshot(overrides: dict[str, tuple[float, float]], *, base_rain: float = 1.0):
    """A single-district snapshot; ``overrides`` maps ISO date -> (rain_mm, gust)."""
    days: list[WeatherDay] = []
    day = START
    while day <= END:
        iso = day.isoformat()
        rain, gust = overrides.get(iso, (base_rain, 20.0))
        days.append(
            WeatherDay(date=iso, precipitation_mm=rain, wind_gust_kmh=gust, temp_max_c=33.0)
        )
        day += timedelta(days=1)
    district = SnapshotDistrict(
        name="Cuddalore",
        lat=LAT,
        lon=LON,
        source_url="https://api.open-meteo.com/v1/forecast?latitude=11.748&longitude=79.7714",
        daily=days,
        notable=[iso for iso, (r, g) in overrides.items() if r >= 10 or g >= 45],
    )
    return WeatherSnapshot(
        generated_at="2026-09-05T11:00:00+00:00",
        days=60,
        coverage=WeatherWindow(start=START.isoformat(), end=END.isoformat()),
        districts=[district],
        citations=[
            Citation(
                id="W-Cuddalore",
                title="Open-Meteo daily weather for Cuddalore",
                url=district.source_url,
                publisher="Open-Meteo",
                as_of="2026-09-05",
                kind="weather",
            ),
            Citation(
                id="W-open-meteo-docs",
                title="Open-Meteo docs",
                url="https://open-meteo.com/en/docs",
                publisher="Open-Meteo",
                as_of="2026-09-05",
                kind="weather",
            ),
        ],
    )


@pytest.fixture
def fake_snapshot(monkeypatch):
    """Install a synthetic snapshot, controllable per test."""

    def install(overrides, *, base_rain: float = 1.0):
        snap = _snapshot(overrides, base_rain=base_rain)
        monkeypatch.setattr(weather, "load_snapshot", lambda: snap)
        return snap

    return install


# --------------------------------------------------------------------------- #
# cyclone
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("gust", "expected"),
    [(75.0, "supported"), (50.0, "partially_supported"), (30.0, "not_supported")],
)
def test_cyclone_thresholds(fake_snapshot, gust, expected):
    fake_snapshot({EVENT: (5.0, gust)})
    result = weather.check_weather(LAT, LON, EVENT, "cyclone")
    assert result.verdict == expected
    assert result.metrics["max_gust_kmh"] == gust
    assert result.source == "snapshot"


# --------------------------------------------------------------------------- #
# flood / inundation
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("day1", "day2", "expected"),
    [(80.0, 60.0, "supported"), (40.0, 30.0, "partially_supported"), (5.0, 5.0, "not_supported")],
)
@pytest.mark.parametrize("damage", ["flood", "inundation"])
def test_flood_two_day_thresholds(fake_snapshot, day1, day2, expected, damage):
    fake_snapshot({EVENT: (day1, 20.0), "2026-08-16": (day2, 20.0)})
    result = weather.check_weather(LAT, LON, EVENT, damage)
    assert result.verdict == expected
    assert result.metrics["best_2day_rain_mm"] == pytest.approx(day1 + day2, abs=1.1)


# --------------------------------------------------------------------------- #
# heavy / unseasonal rain
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("rain", "expected"),
    [(60.0, "supported"), (30.0, "partially_supported"), (5.0, "not_supported")],
)
@pytest.mark.parametrize("damage", ["heavy_rain", "unseasonal_rain"])
def test_rain_day_thresholds(fake_snapshot, rain, expected, damage):
    fake_snapshot({EVENT: (rain, 20.0)})
    result = weather.check_weather(LAT, LON, EVENT, damage)
    assert result.verdict == expected
    assert result.metrics["max_daily_rain_mm"] == rain


# --------------------------------------------------------------------------- #
# drought
# --------------------------------------------------------------------------- #
def test_drought_supported_when_window_far_below_baseline(fake_snapshot):
    # 60 days at 5 mm gives a 45-day baseline of 225 mm; the window is zeroed out.
    dry = {
        (END - timedelta(days=i)).isoformat(): (0.0, 15.0) for i in range(45)
    }
    fake_snapshot(dry, base_rain=5.0)
    result = weather.check_weather(LAT, LON, END.isoformat(), "drought")
    assert result.verdict == "supported"
    assert result.metrics["window_rain_mm"] == 0.0
    assert result.metrics["baseline_45d_rain_mm"] > 0
    # The honest explanation of the baseline must be in the reasons.
    assert any("baseline" in reason.lower() for reason in result.reasons)


def test_drought_not_supported_in_a_normal_window(fake_snapshot):
    fake_snapshot({}, base_rain=5.0)
    result = weather.check_weather(LAT, LON, END.isoformat(), "drought")
    assert result.verdict == "not_supported"


def test_drought_partially_supported_between_30_and_60_percent(fake_snapshot):
    # Baseline daily average lands near 4.25 mm; the window runs at ~2 mm a day.
    window = {(END - timedelta(days=i)).isoformat(): (2.0, 15.0) for i in range(45)}
    fake_snapshot(window, base_rain=11.0)
    result = weather.check_weather(LAT, LON, END.isoformat(), "drought")
    assert result.verdict == "partially_supported"
    assert 0.30 <= result.metrics["drought_ratio"] < 0.60


# --------------------------------------------------------------------------- #
# weather-neutral damage types
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("damage", ["hailstorm", "pest", "disease", "fire", "landslide", "other"])
def test_neutral_types_are_unverifiable_when_calm(fake_snapshot, damage):
    fake_snapshot({})
    result = weather.check_weather(LAT, LON, EVENT, damage)
    assert result.verdict == "unverifiable"
    assert any("field evidence" in r for r in result.reasons)


@pytest.mark.parametrize("damage", ["hailstorm", "pest", "fire"])
def test_neutral_types_are_partial_when_weather_was_rough(fake_snapshot, damage):
    fake_snapshot({EVENT: (25.0, 55.0)})
    result = weather.check_weather(LAT, LON, EVENT, damage)
    assert result.verdict == "partially_supported"


# --------------------------------------------------------------------------- #
# coverage, geography and outages
# --------------------------------------------------------------------------- #
def test_date_outside_coverage_is_unverifiable_and_says_the_dates(fake_snapshot):
    fake_snapshot({})
    result = weather.check_weather(LAT, LON, "2018-11-16", "cyclone")
    assert result.verdict == "unverifiable"
    assert result.source == "none"
    joined = " ".join(result.reasons)
    assert START.isoformat() in joined and END.isoformat() in joined


def test_place_outside_tamil_nadu_is_unverifiable(fake_snapshot):
    fake_snapshot({})
    result = weather.check_weather(19.076, 72.877, EVENT, "cyclone")  # Mumbai
    assert result.verdict == "unverifiable"
    assert "outside" in " ".join(result.reasons)


def test_data_down_is_unverifiable_without_reading_the_snapshot(fake_snapshot):
    fake_snapshot({EVENT: (200.0, 120.0)})
    result = weather.check_weather(LAT, LON, EVENT, "cyclone", data_down=True)
    assert result.verdict == "unverifiable"
    assert result.metrics == {}


def test_unparseable_date_is_unverifiable(fake_snapshot):
    fake_snapshot({})
    result = weather.check_weather(LAT, LON, "last Tuesday", "flood")
    assert result.verdict == "unverifiable"


# --------------------------------------------------------------------------- #
# supporting output
# --------------------------------------------------------------------------- #
def test_nearby_matching_dates_are_nearest_first_and_capped(fake_snapshot):
    overrides = {
        "2026-08-18": (5.0, 80.0),
        "2026-08-10": (5.0, 80.0),
        "2026-07-20": (5.0, 80.0),
        "2026-07-12": (5.0, 80.0),
        "2026-07-08": (5.0, 80.0),
        "2026-07-09": (5.0, 80.0),
    }
    fake_snapshot(overrides)
    result = weather.check_weather(LAT, LON, EVENT, "cyclone")
    assert result.nearby_matching_dates[:2] == ["2026-08-18", "2026-08-10"]
    assert len(result.nearby_matching_dates) <= weather.MAX_NEARBY_DATES


def test_evidence_carries_window_chart_and_citations(fake_snapshot):
    fake_snapshot({EVENT: (60.0, 30.0)})
    result = weather.check_weather(LAT, LON, EVENT, "heavy_rain")
    assert result.window.start == "2026-08-13" and result.window.end == "2026-08-17"
    assert 20 <= len(result.daily) <= 29  # +/- 14 days, clipped to coverage
    assert {c.id for c in result.citations} == {"W-Cuddalore", "W-open-meteo-docs"}
    assert result.request_url and result.request_url.startswith("https://api.open-meteo.com")
    assert result.context_30d_rain_mm is not None
    assert result.farmer_sentence


def test_fetch_daily_slices_the_snapshot(fake_snapshot):
    fake_snapshot({})
    days, url = weather.fetch_daily(LAT, LON, "2026-08-01", "2026-08-05")
    assert [d.date for d in days] == [
        "2026-08-01", "2026-08-02", "2026-08-03", "2026-08-04", "2026-08-05"
    ]
    assert url.startswith("https://api.open-meteo.com")


def test_fetch_daily_outside_tamil_nadu_returns_nothing(fake_snapshot):
    fake_snapshot({})
    days, url = weather.fetch_daily(19.076, 72.877, "2026-08-01", "2026-08-05")
    assert days == [] and url == ""


def test_haversine_matches_a_known_distance():
    # Chennai to Madurai is roughly 420 km great-circle.
    km = weather.haversine_km(13.0827, 80.2707, 9.9252, 78.1198)
    assert 400 < km < 440
