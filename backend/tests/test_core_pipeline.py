"""End-to-end ingest via POST /api/admin/simulate, offline.

The weather verdict is stubbed in the mismatch tests so the decision logic is
exercised deterministically whether or not the data worker's snapshot happens to
support the transcript on the day the suite runs.
"""

from __future__ import annotations

from datetime import date

import pytest

from app import providers
from app.events import recent_events
from app.schemas import Citation, DisasterEvidence, WeatherEvidence
from services import ingest

MISMATCH_TRANSCRIPT = """Agent: Namaskaram, this is Sunil from the crop insurance help desk. Please tell me what happened.
Caller: Sir thisis Murugan from Cuddalore district. On 12 August a cyclone destroyed mypaddy crop.
Agent: I am sorry. How much land is affected?
Caller: Two acres sir. Everything is flattened.
Agent: Thank you. I have noted two acres of paddy in Cuddalore, damaged on 12 August.
Caller: Yes sir. How much money will I get?
Agent: I cannot tell you any amount. The insurance company decides that after a field survey.
Agent: Please keep photos of the damaged crop and your land record ready.
"""

CLEAN_TRANSCRIPT = """Agent: Hello, this is Sunil from the crop insurance help desk.
Caller: My name is Selvi from Thanjavur. Heavy rain damaged my paddy on 20 August.
Agent: How much land is affected?
Caller: One acre.
Agent: Thank you, I have recorded one acre of paddy in Thanjavur damaged on 20 August by heavy rain.
"""


def stub_weather(verdict: str) -> WeatherEvidence:
    return WeatherEvidence(
        source="snapshot",
        request_url="https://api.open-meteo.com/v1/forecast?stub=1",
        window={"start": "2026-08-10", "end": "2026-08-14"},
        daily=[{"date": "2026-08-12", "precipitation_mm": 4.0,
                "wind_gust_kmh": 29.0, "temp_max_c": 33.0}],
        metrics={"max_gust_kmh": 29.0, "rain_2day_mm": 4.0, "district_used": "Cuddalore"},
        verdict=verdict,  # type: ignore[arg-type]
        reasons=["Maximum gust 29 km/h is well below the 60 km/h cyclone threshold."],
        farmer_sentence=(
            "The weather record for Cuddalore on 12 August shows 4 mm of rain and "
            "29 km/h wind, which does not match a cyclone."
        ),
        nearby_matching_dates=[],
        citations=[Citation(id="W-Cuddalore-2026-08-12", title="Open-Meteo daily record",
                            url="https://api.open-meteo.com/v1/forecast",
                            publisher="Open-Meteo", as_of="2026-09-05", kind="weather")],
    )


@pytest.fixture
def stub_not_supported(monkeypatch):
    monkeypatch.setattr(
        providers, "check_weather", lambda *a, **k: stub_weather("not_supported")
    )
    monkeypatch.setattr(
        providers, "check_disasters", lambda *a, **k: DisasterEvidence(source="none")
    )


# --------------------------------------------------------------------------
# the headline path: mismatched weather -> claim + ticket
# --------------------------------------------------------------------------
def test_simulate_produces_claim_and_ticket_for_mismatched_weather(client, stub_not_supported):
    response = client.post("/api/admin/simulate", json={"transcript": MISMATCH_TRANSCRIPT})
    assert response.status_code == 200
    call = response.json()

    assert call["direction"] == "simulated"
    assert call["processing"] == "done"
    assert call["claim_id"] is not None
    assert call["ticket_id"] is not None
    assert len(call["transcript"]) == 8

    claim = client.get(f"/api/claims/{call['claim_id']}").json()
    assert claim["reference"].startswith("VST-")
    assert claim["status"] == "escalated"
    assert claim["crop"] == "paddy"
    assert claim["damage_type"] == "cyclone"
    assert claim["event_date"] == "2026-08-12"
    assert claim["location"]["district"] == "Cuddalore"
    assert claim["land_extent"]["value"] == 2
    assert claim["land_extent"]["hectares"] == pytest.approx(0.809, abs=0.01)

    assert claim["weather_evidence"]["verdict"] == "not_supported"
    assert claim["risk"]["score"] >= 40
    assert claim["risk"]["level"] == "high"
    assert "weather_not_supported" in {s["code"] for s in claim["risk"]["signals"]}
    assert claim["evidence_required"], "a checklist must be attached"

    tickets = client.get("/api/tickets").json()
    assert len(tickets) == 1
    ticket = tickets[0]
    assert ticket["claim_id"] == claim["id"]
    assert ticket["status"] == "open"
    assert ticket["reference"] == claim["reference"]
    assert ticket["farmer_explanation"]
    # the explanation must be non-accusatory
    lowered = ticket["farmer_explanation"].lower()
    assert "fraud" not in lowered and "false" not in lowered and "lying" not in lowered
    assert "does not mean your claim is refused" in lowered


def test_pipeline_emits_events_in_order(client, stub_not_supported):
    client.post("/api/admin/simulate", json={"transcript": MISMATCH_TRANSCRIPT})
    types = [event["type"] for event in recent_events()]

    assert "call.completed" in types
    assert "claim.created" in types
    assert "claim.updated" in types
    assert "ticket.created" in types
    # partial claim first, evidence blocks after, ticket last
    assert types.index("claim.created") < types.index("claim.updated")
    assert types.index("claim.updated") < types.index("ticket.created")

    stages = [
        event["payload"].get("stage")
        for event in recent_events("claim.updated")
    ]
    assert stages[:5] == ["location", "weather", "disasters", "crop", "schemes"]
    assert stages[-1] == "decided"


def test_agent_refusal_produces_no_guardrail_incident(client, stub_not_supported):
    """This transcript contains a correct refusal — it must stay clean."""
    response = client.post("/api/admin/simulate", json={"transcript": MISMATCH_TRANSCRIPT})
    assert response.json()["guardrail_incidents"] == []


def test_promise_in_transcript_creates_an_incident(client, stub_not_supported):
    transcript = MISMATCH_TRANSCRIPT.replace(
        "Agent: I cannot tell you any amount. The insurance company decides that after a field survey.",
        "Agent: You will definitely get twenty thousand rupees within ten days.",
    )
    call = client.post("/api/admin/simulate", json={"transcript": transcript}).json()
    categories = {incident["category"] for incident in call["guardrail_incidents"]}
    assert "payout_promise" in categories

    stats = client.get("/api/stats").json()
    assert stats["guardrail_incidents"] >= 1


# --------------------------------------------------------------------------
# escalation triggers that do not depend on weather
# --------------------------------------------------------------------------
def test_asking_for_a_human_escalates(client, monkeypatch):
    monkeypatch.setattr(providers, "check_weather", lambda *a, **k: stub_weather("supported"))
    transcript = (
        "Agent: Hello, how can I help?\n"
        "Caller: I want to talk to a person, not a machine.\n"
        "Agent: A person will call you back.\n"
    )
    call = client.post("/api/admin/simulate", json={"transcript": transcript}).json()
    claim = client.get(f"/api/claims/{call['claim_id']}").json()
    assert claim["status"] == "escalated"
    assert "asked_for_human" in {s["code"] for s in claim["risk"]["signals"]}


def test_data_down_mode_forces_escalation_never_verified(client):
    client.post("/api/admin/data-down", json={"enabled": True})
    try:
        call = client.post("/api/admin/simulate", json={"transcript": CLEAN_TRANSCRIPT}).json()
        claim = client.get(f"/api/claims/{call['claim_id']}").json()
        assert claim["weather_evidence"]["verdict"] != "supported"
        assert claim["status"] == "escalated"
    finally:
        client.post("/api/admin/data-down", json={"enabled": False})


def test_reference_numbers_are_sequential(client, stub_not_supported):
    first = client.post("/api/admin/simulate", json={"transcript": CLEAN_TRANSCRIPT}).json()
    second = client.post("/api/admin/simulate", json={"transcript": CLEAN_TRANSCRIPT}).json()
    year = date.today().year
    ref_one = client.get(f"/api/claims/{first['claim_id']}").json()["reference"]
    ref_two = client.get(f"/api/claims/{second['claim_id']}").json()["reference"]
    assert ref_one == f"VST-{year}-0001"
    assert ref_two == f"VST-{year}-0002"


# --------------------------------------------------------------------------
# risk scoring in isolation
# --------------------------------------------------------------------------
def test_risk_scoring_rules():
    risk = ingest.score_risk(
        weather_verdict="not_supported",
        contradictions=["two dates given"],
        hectares=25.0,
        crop_in_window=False,
        event_date="2026-08-01",
        call_date=date(2026, 9, 5),
        damage_type="hailstorm",
        distress=False,
        asked_for_human=False,
        unknown_citations=["S99"],
    )
    codes = {signal.code for signal in risk.signals}
    assert codes == {
        "weather_not_supported", "contradiction", "large_extent",
        "crop_out_of_window", "late_intimation", "unknown_citation",
    }
    assert risk.score == 40 + 15 + 15 + 15 + 5 + 20
    assert risk.level == "high"


def test_clean_claim_scores_low():
    risk = ingest.score_risk(
        weather_verdict="supported",
        contradictions=[],
        hectares=0.8,
        crop_in_window=True,
        event_date="2026-09-03",
        call_date=date(2026, 9, 5),
        damage_type="cyclone",
        distress=False,
        asked_for_human=False,
        unknown_citations=[],
    )
    assert risk.score == 0
    assert risk.level == "low"


def test_unverifiable_weather_never_reads_as_verified():
    risk = ingest.score_risk(
        weather_verdict="unverifiable", contradictions=[], hectares=None,
        crop_in_window=None, event_date=None, call_date=date(2026, 9, 5),
        damage_type=None, distress=False, asked_for_human=False, unknown_citations=[],
    )
    assert risk.score == 25
    assert "weather_unverifiable" in {s.code for s in risk.signals}
