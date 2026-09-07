"""GDACS cross-check, read only from the snapshot."""

from __future__ import annotations

import pytest

from services import disasters
from services.models import DisasterEvent, WeatherSnapshot, WeatherWindow

CUDDALORE = (11.748, 79.7714)


def _snapshot(events: list[DisasterEvent]) -> WeatherSnapshot:
    return WeatherSnapshot(
        generated_at="2026-09-05T11:00:00+00:00",
        days=60,
        coverage=WeatherWindow(start="2026-07-07", end="2026-09-04"),
        disasters=events,
    )


def _event(eid: str, lat: float, lon: float, start: str, end: str, etype: str = "FL"):
    return DisasterEvent(
        id=eid,
        type=etype,
        name=f"{etype} in India",
        alert_level="Orange",
        **{"from": start},
        to=end,
        report_url=f"https://www.gdacs.org/report.aspx?eventid={eid}",
        lat=lat,
        lon=lon,
    )


@pytest.fixture
def fake_snapshot(monkeypatch):
    def install(events):
        snap = _snapshot(events)
        monkeypatch.setattr(disasters, "load_snapshot", lambda: snap)
        return snap

    return install


def test_a_nearby_overlapping_event_is_returned(fake_snapshot):
    fake_snapshot([_event("1", 11.9, 79.8, "2026-08-10", "2026-08-20")])
    evidence = disasters.check_disasters(*CUDDALORE, "2026-08-15")
    assert evidence.source == "gdacs"
    assert [e.id for e in evidence.events] == ["1"]
    assert evidence.events[0].distance_km is not None
    assert evidence.events[0].distance_km < 30


def test_a_far_away_event_is_excluded(fake_snapshot):
    fake_snapshot([_event("1", 29.35, 79.55, "2026-08-09", "2026-09-02")])  # Uttarakhand
    evidence = disasters.check_disasters(*CUDDALORE, "2026-08-15")
    assert evidence.events == []
    assert evidence.source == "gdacs"


def test_an_event_outside_the_date_window_is_excluded(fake_snapshot):
    fake_snapshot([_event("1", 11.9, 79.8, "2026-07-01", "2026-07-05")])
    evidence = disasters.check_disasters(*CUDDALORE, "2026-08-15")
    assert evidence.events == []


def test_the_days_slack_widens_the_date_window(fake_snapshot):
    fake_snapshot([_event("1", 11.9, 79.8, "2026-08-01", "2026-08-12")])
    assert disasters.check_disasters(*CUDDALORE, "2026-08-15", days=5).events
    assert not disasters.check_disasters(*CUDDALORE, "2026-08-15", days=1).events


def test_events_come_back_nearest_first(fake_snapshot):
    fake_snapshot([
        _event("far", 13.5, 80.2, "2026-08-10", "2026-08-20"),
        _event("near", 11.8, 79.8, "2026-08-10", "2026-08-20"),
    ])
    evidence = disasters.check_disasters(*CUDDALORE, "2026-08-15")
    assert [e.id for e in evidence.events] == ["near", "far"]


def test_radius_is_respected(fake_snapshot):
    fake_snapshot([_event("1", 13.5, 80.2, "2026-08-10", "2026-08-20")])
    assert disasters.check_disasters(*CUDDALORE, "2026-08-15", radius_km=300).events
    assert not disasters.check_disasters(*CUDDALORE, "2026-08-15", radius_km=50).events


def test_citations_include_report_urls_and_the_gdacs_home(fake_snapshot):
    fake_snapshot([_event("1104121", 11.9, 79.8, "2026-08-10", "2026-08-20")])
    evidence = disasters.check_disasters(*CUDDALORE, "2026-08-15")
    ids = {c.id for c in evidence.citations}
    assert "D-1104121" in ids and "D-gdacs" in ids
    by_id = {c.id: c for c in evidence.citations}
    assert by_id["D-1104121"].url.startswith("https://www.gdacs.org/report.aspx")
    assert by_id["D-gdacs"].url == "https://www.gdacs.org"
    assert all(c.kind == "disaster" for c in evidence.citations)


def test_data_down_returns_an_empty_none_source(fake_snapshot):
    fake_snapshot([_event("1", 11.9, 79.8, "2026-08-10", "2026-08-20")])
    evidence = disasters.check_disasters(*CUDDALORE, "2026-08-15", data_down=True)
    assert evidence.source == "none"
    assert evidence.events == [] and evidence.citations == []


def test_a_bad_date_returns_an_empty_none_source(fake_snapshot):
    fake_snapshot([_event("1", 11.9, 79.8, "2026-08-10", "2026-08-20")])
    evidence = disasters.check_disasters(*CUDDALORE, "not a date")
    assert evidence.source == "none"


def test_the_real_snapshot_can_be_queried_without_network():
    """Whatever GDACS returned, the call must succeed and stay offline."""
    evidence = disasters.check_disasters(*CUDDALORE, "2026-08-15")
    assert evidence.source in {"gdacs", "none"}
    for event in evidence.events:
        assert event.report_url.startswith("http")
