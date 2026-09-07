"""Evidence link creation, the farmer page, and uploads."""

from __future__ import annotations

import io
import re

import pytest

from app.config import settings
from app.events import recent_events
from services import evidence as evidence_service

TRANSCRIPT = """Agent: Hello, this is Sunil from the crop insurance help desk.
Caller: My name is Kavitha from Thanjavur. Heavy rain damaged my paddy on 20 August.
Agent: How much land is affected?
Caller: One acre.
"""


@pytest.fixture
def claim_id(client) -> int:
    call = client.post(
        "/api/admin/simulate",
        json={"transcript": TRANSCRIPT, "from_number": "+919876543210"},
    ).json()
    assert call["claim_id"] is not None
    return call["claim_id"]


def png_bytes() -> bytes:
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (24, 24), (12, 120, 40)).save(buffer, format="PNG")
    return buffer.getvalue()


# --------------------------------------------------------------------------
# link
# --------------------------------------------------------------------------
def test_evidence_link_has_token_url_qr_and_whatsapp(client, claim_id):
    response = client.post(f"/api/claims/{claim_id}/evidence-link")
    assert response.status_code == 200
    link = response.json()

    assert len(link["token"]) >= 20
    assert link["url"].endswith(f"/e/{link['token']}")
    assert link["url"].startswith(settings.public_base_url.rstrip("/"))
    assert link["expires_at"]

    assert link["qr_svg"].lstrip().startswith("<?xml") or "<svg" in link["qr_svg"]
    assert "<svg" in link["qr_svg"]

    assert link["whatsapp_url"].startswith("https://wa.me/919876543210?text=")
    assert "%20" in link["whatsapp_url"]
    # the message carries the upload link, fully percent-encoded
    assert "%2Fe%2F" in link["whatsapp_url"]
    assert link["token"] in link["whatsapp_url"]


def test_whatsapp_message_is_english_and_mentions_the_reference():
    from urllib.parse import parse_qs, urlparse

    url = evidence_service.whatsapp_url("+91 89391 53390", "http://x/e/tok", "VST-2026-0007")
    text = parse_qs(urlparse(url).query)["text"][0]
    assert "VST-2026-0007" in text
    assert "http://x/e/tok" in text
    assert re.search(r"[A-Za-z]{4,}", text)


def test_link_for_unknown_claim_is_404(client):
    assert client.post("/api/claims/98765/evidence-link").status_code == 404


# --------------------------------------------------------------------------
# page
# --------------------------------------------------------------------------
def test_evidence_page_lists_the_checklist(client, claim_id):
    token = client.post(f"/api/claims/{claim_id}/evidence-link").json()["token"]
    page = client.get(f"/api/evidence/{token}").json()

    assert page["claim_reference"].startswith("VST-")
    assert page["farmer_language"]
    assert page["items"], "the claim's evidence checklist must be present"
    first = page["items"][0]
    for field in ("key", "label", "label_local", "instructions_local", "required", "uploaded"):
        assert field in first
    # offline: local fields fall back to English rather than being blank
    assert first["label_local"]
    assert first["instructions_local"]
    assert first["uploaded"] == []


def test_bad_token_is_404(client):
    assert client.get("/api/evidence/not-a-real-token").status_code == 404


# --------------------------------------------------------------------------
# upload
# --------------------------------------------------------------------------
def test_upload_stores_the_file_and_attaches_it_to_the_claim(client, claim_id):
    token = client.post(f"/api/claims/{claim_id}/evidence-link").json()["token"]
    page = client.get(f"/api/evidence/{token}").json()
    item_key = page["items"][0]["key"]
    data = png_bytes()

    response = client.post(
        f"/api/evidence/{token}/upload",
        data={"item_key": item_key, "client_time": "2026-09-05T10:30:00+05:30",
              "lat": "11.7480", "lon": "79.7714"},
        files={"file": ("damage.png", data, "image/png")},
    )
    assert response.status_code == 200
    uploaded = response.json()

    assert uploaded["item_key"] == item_key
    assert uploaded["filename"] == "damage.png"
    assert uploaded["content_type"] == "image/png"
    assert uploaded["size"] == len(data)
    assert uploaded["quality_flag"] == "unchecked"
    assert uploaded["lat"] == pytest.approx(11.748)
    assert uploaded["url"] == f"/api/evidence/files/{uploaded['id']}"

    # the binary is served back
    binary = client.get(uploaded["url"])
    assert binary.status_code == 200
    assert binary.content == data

    # and it is attached to the claim and shown on the page
    claim = client.get(f"/api/claims/{claim_id}").json()
    assert [f["id"] for f in claim["evidence_uploads"]] == [uploaded["id"]]

    page = client.get(f"/api/evidence/{token}").json()
    item = next(i for i in page["items"] if i["key"] == item_key)
    assert len(item["uploaded"]) == 1

    events = [e for e in recent_events("evidence.uploaded")]
    assert events and events[-1]["payload"]["claim_id"] == claim_id


def test_upload_rejects_unsupported_types(client, claim_id):
    token = client.post(f"/api/claims/{claim_id}/evidence-link").json()["token"]
    response = client.post(
        f"/api/evidence/{token}/upload",
        data={"item_key": "damage_photos"},
        files={"file": ("notes.exe", b"MZ\x00\x00", "application/x-msdownload")},
    )
    assert response.status_code == 400
    assert "photos" in response.json()["detail"].lower()


def test_upload_rejects_oversized_files(client, claim_id, monkeypatch):
    monkeypatch.setattr(settings, "max_upload_bytes", 1024)
    token = client.post(f"/api/claims/{claim_id}/evidence-link").json()["token"]
    response = client.post(
        f"/api/evidence/{token}/upload",
        data={"item_key": "damage_photos"},
        files={"file": ("big.png", b"x" * 4096, "image/png")},
    )
    assert response.status_code in (400, 413)


def test_upload_to_a_bad_token_is_404(client):
    response = client.post(
        "/api/evidence/nope/upload",
        data={"item_key": "damage_photos"},
        files={"file": ("a.png", png_bytes(), "image/png")},
    )
    assert response.status_code in (400, 404)


def test_pdf_is_accepted(client, claim_id):
    token = client.post(f"/api/claims/{claim_id}/evidence-link").json()["token"]
    response = client.post(
        f"/api/evidence/{token}/upload",
        data={"item_key": "land_record"},
        files={"file": ("chitta.pdf", b"%PDF-1.4 fake", "application/pdf")},
    )
    assert response.status_code == 200
    assert response.json()["content_type"] == "application/pdf"


def test_expired_token_is_rejected(client, claim_id):
    from app.db import EvidenceTokenRow, session_scope

    token = client.post(f"/api/claims/{claim_id}/evidence-link").json()["token"]
    with session_scope() as session:
        session.get(EvidenceTokenRow, token).expires_at = "2020-01-01T00:00:00+00:00"

    response = client.get(f"/api/evidence/{token}")
    assert response.status_code == 404
    assert "expired" in response.json()["detail"].lower()
