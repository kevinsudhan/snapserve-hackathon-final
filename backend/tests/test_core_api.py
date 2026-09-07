"""HTTP surface: health, stats, calls, claims, tickets, citations, admin, ws."""

from __future__ import annotations

from app import __version__
from services import poller

TRANSCRIPT = """Agent: Hello, this is Sunil from the crop insurance help desk.
Caller: My name is Anand from Cuddalore. Heavy rain damaged my paddy on 20 August.
Agent: How much land is affected?
Caller: Two acres.
"""


def make_claim(client) -> dict:
    call = client.post("/api/admin/simulate", json={"transcript": TRANSCRIPT}).json()
    return client.get(f"/api/claims/{call['claim_id']}").json()


# --------------------------------------------------------------------------
# health / stats
# --------------------------------------------------------------------------
def test_health(client):
    body = client.get("/api/health").json()
    assert body["ok"] is True
    assert body["version"] == __version__
    assert body["gemini_ok"] is False  # GEMINI_DISABLED in tests
    assert body["data_down_mode"] is False
    assert set(body["poller"]) >= {"running", "last_poll_at"}


def test_health_modules_reports_sibling_availability(client):
    modules = client.get("/api/health/modules").json()["modules"]
    assert set(modules) == {
        "gazetteer", "weather", "disasters", "crops", "schemes", "knowledge_weather"
    }
    assert all(isinstance(value, bool) for value in modules.values())


def test_stats_shape_and_counts(client):
    empty = client.get("/api/stats").json()
    assert empty["calls_total"] == 0
    assert set(empty["verdicts"]) == {
        "supported", "partially_supported", "not_supported", "unverifiable"
    }
    assert len(empty["last_24h"]) == 24

    make_claim(client)
    after = client.get("/api/stats").json()
    assert after["calls_total"] == 1
    assert after["claims_total"] == 1
    assert sum(after["languages"].values()) == 1


# --------------------------------------------------------------------------
# calls
# --------------------------------------------------------------------------
def test_calls_list_and_detail(client):
    client.post("/api/admin/simulate", json={"transcript": TRANSCRIPT})
    calls = client.get("/api/calls?limit=10").json()
    assert len(calls) == 1
    call = calls[0]
    assert call["status"] == "completed"
    assert call["processing"] == "done"
    assert call["transcript"][0]["role"] == "agent"

    detail = client.get(f"/api/calls/{call['id']}").json()
    assert detail["id"] == call["id"]
    assert client.get("/api/calls/999999").status_code == 404


# --------------------------------------------------------------------------
# claims
# --------------------------------------------------------------------------
def test_claims_filtering_and_search(client):
    claim = make_claim(client)

    assert len(client.get("/api/claims").json()) == 1
    assert client.get(f"/api/claims?status={claim['status']}").json()
    assert client.get("/api/claims?status=closed").json() == []
    assert client.get("/api/claims?q=cuddalore").json()
    assert client.get("/api/claims?q=zzzznotfound").json() == []
    assert client.get(f"/api/claims?q={claim['reference']}").json()


def test_claims_list_trims_the_daily_series(client):
    make_claim(client)
    listed = client.get("/api/claims").json()[0]
    assert listed["weather_evidence"]["daily"] == []
    # the detail view keeps everything
    detail = client.get(f"/api/claims/{listed['id']}").json()
    assert "daily" in detail["weather_evidence"]


def test_patch_claim_sets_status_and_notes(client):
    claim = make_claim(client)
    response = client.patch(
        f"/api/claims/{claim['id']}",
        json={"status": "under_review", "reviewer_notes": "Called the farmer back."},
    )
    assert response.status_code == 200
    updated = response.json()
    assert updated["status"] == "under_review"
    assert updated["reviewer_notes"] == "Called the farmer back."
    assert updated["updated_at"] >= claim["updated_at"]

    assert client.patch("/api/claims/999999", json={"status": "closed"}).status_code == 404


def test_claim_detail_has_every_contract_block(client):
    claim = make_claim(client)
    for field in (
        "reference", "call_id", "status", "farmer", "location", "narrative",
        "weather_evidence", "disaster_evidence", "scheme_matches", "unknowns",
        "evidence_required", "evidence_uploads", "risk", "agent_said_facts",
        "created_at", "updated_at",
    ):
        assert field in claim, field
    assert claim["weather_evidence"]["verdict"] in (
        "supported", "partially_supported", "not_supported", "unverifiable"
    )


# --------------------------------------------------------------------------
# tickets
# --------------------------------------------------------------------------
def test_ticket_patch_and_filter(client):
    client.post("/api/admin/data-down", json={"enabled": True})
    try:
        make_claim(client)  # unverifiable -> escalated -> ticket
    finally:
        client.post("/api/admin/data-down", json={"enabled": False})

    tickets = client.get("/api/tickets").json()
    assert len(tickets) == 1
    ticket = tickets[0]

    assert client.get("/api/tickets?status=open").json()
    assert client.get("/api/tickets?status=resolved").json() == []

    updated = client.patch(
        f"/api/tickets/{ticket['id']}",
        json={"status": "in_review", "reviewer_notes": "Assigned to field officer."},
    ).json()
    assert updated["status"] == "in_review"
    assert updated["reviewer_notes"] == "Assigned to field officer."
    assert client.patch("/api/tickets/999999", json={"status": "resolved"}).status_code == 404


# --------------------------------------------------------------------------
# citations / knowledge / eval
# --------------------------------------------------------------------------
def test_unknown_citation_is_404(client):
    assert client.get("/api/citations/S-does-not-exist").status_code == 404


def test_knowledge_prompt_and_status(client):
    prompt = client.get("/api/knowledge/prompt").json()
    assert prompt["system_prompt"].strip()
    assert prompt["approx_tokens"] > 0

    status = client.get("/api/knowledge/status").json()
    for field in ("last_refresh_at", "agent_synced_at", "districts", "days",
                  "notable_events", "approx_tokens", "sources"):
        assert field in status


def test_eval_stubs(client):
    assert client.get("/api/eval/latest").json() is None
    assert client.post("/api/eval/run", json={}).status_code == 501


# --------------------------------------------------------------------------
# admin
# --------------------------------------------------------------------------
def test_data_down_toggle(client):
    assert client.post("/api/admin/data-down", json={"enabled": True}).json() == {"enabled": True}
    assert client.get("/api/health").json()["data_down_mode"] is True
    assert client.post("/api/admin/data-down", json={"enabled": False}).json() == {"enabled": False}


def test_reset_demo_clears_calls_claims_and_tickets(client):
    make_claim(client)
    assert client.get("/api/calls").json()

    cleared = client.post("/api/admin/reset-demo").json()["cleared"]
    assert cleared["calls"] == 1
    assert cleared["claims"] == 1

    assert client.get("/api/calls").json() == []
    assert client.get("/api/claims").json() == []
    assert client.get("/api/tickets").json() == []
    # knowledge survives
    assert client.get("/api/knowledge/prompt").json()["approx_tokens"] > 0


# --------------------------------------------------------------------------
# websocket
# --------------------------------------------------------------------------
def test_websocket_accepts_ping(client):
    with client.websocket_connect("/ws/events") as socket:
        hello = socket.receive_json()
        assert hello["type"] == "poller.status"
        socket.send_json({"type": "ping"})
        assert socket.receive_json()["type"] == "pong"


def test_websocket_receives_pipeline_events(client):
    with client.websocket_connect("/ws/events") as socket:
        socket.receive_json()  # hello
        client.post("/api/admin/simulate", json={"transcript": TRANSCRIPT})
        seen = {socket.receive_json()["type"] for _ in range(4)}
    assert "call.completed" in seen or "claim.created" in seen


# --------------------------------------------------------------------------
# poller mapping (no network)
# --------------------------------------------------------------------------
def test_status_mapping_handles_unknown_vocabulary():
    assert poller.map_status("completed", "2026-09-05T10:00:00Z") == "completed"
    assert poller.map_status("failed", None) == "failed"
    assert poller.map_status("no_pickup", None) == "no_pickup"
    assert poller.map_status("ringing", None) == "in_progress"
    # an unknown status is judged by whether the call has ended
    assert poller.map_status("something_new", None) == "in_progress"
    assert poller.map_status("something_new", "2026-09-05T10:00:00Z") == "completed"


def test_metadata_is_parsed_from_its_json_string():
    parsed = poller.parse_metadata('{"externalCallId": "abc", "direction": "outbound"}')
    assert parsed["externalCallId"] == "abc"
    assert poller.parse_metadata("not json") == {}
    assert poller.parse_metadata(None) == {}


def test_call_fields_maps_the_snapserve_payload():
    fields = poller.call_fields(
        {
            "id": 22845,
            "agentId": 1151,
            "status": "completed",
            "toNumber": "+919876543210",
            "fromNumber": "+917965854267",
            "durationSeconds": 132,
            "transcript": "Agent: Hello\nCaller: Hi",
            "recordingUrl": "/api/storage/recordings/22845",
            "metadata": '{"direction": "inbound", "callerKey": "k1"}',
            "createdAt": "2026-09-05T10:00:00Z",
            "endedAt": "2026-09-05T10:02:12Z",
            "callSummary": "Farmer reported paddy damage.",
        }
    )
    assert fields["snapserve_call_id"] == "22845"
    assert fields["status"] == "completed"
    assert fields["direction"] == "inbound"
    assert fields["duration_seconds"] == 132
    assert fields["recording_url"] == "https://app.snapserve.ai/api/storage/recordings/22845"
    assert fields["summary"] == "Farmer reported paddy damage."
    assert fields["raw"]["metadata"]["callerKey"] == "k1"
