"""Farmer-facing evidence collection: signed links, QR, checklist, uploads.

A link is a ``secrets.token_urlsafe`` token valid for
``EVIDENCE_TOKEN_TTL_DAYS`` (7).  The checklist comes from the claim's
``evidence_required``; the labels are translated once into the farmer's language
via Gemini and cached in the DB, falling back to English.  Uploads land under
``EVIDENCE_DIR/<claim>/<uuid>.<ext>``.
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote

from sqlalchemy import select

from app.config import settings
from app.db import (
    ClaimRow,
    EvidenceFileRow,
    EvidenceTokenRow,
    meta_get,
    meta_set,
    now_iso,
    read_session,
    session_scope,
)
from app.events import emit
from app.schemas import (
    EvidenceChecklistItem,
    EvidenceFile,
    EvidenceItem,
    EvidenceLinkResponse,
    EvidencePage,
    TranslationResult,
    coerce_list,
)
from app.serializers import evidence_file_to_schema, load_evidence_files

logger = logging.getLogger(__name__)

ALLOWED_CONTENT_TYPES = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/heic": ".heic",
    "image/heif": ".heif",
    "image/gif": ".gif",
    "application/pdf": ".pdf",
}

LANGUAGE_NAMES = {
    "ta": "Tamil", "hi": "Hindi", "te": "Telugu", "kn": "Kannada",
    "ml": "Malayalam", "mr": "Marathi", "bn": "Bengali", "gu": "Gujarati",
    "pa": "Punjabi", "or": "Odia", "ur": "Urdu", "en": "English",
}


class EvidenceError(RuntimeError):
    """Bad token, oversized upload, unsupported type."""


# --------------------------------------------------------------------------
# links
# --------------------------------------------------------------------------
def _expiry() -> str:
    return (
        datetime.now(timezone.utc).replace(microsecond=0)
        + timedelta(days=settings.evidence_token_ttl_days)
    ).isoformat()


def evidence_url(token: str) -> str:
    return f"{settings.public_base_url.rstrip('/')}/e/{token}"


def build_qr_svg(url: str) -> str:
    """QR as an inline SVG string (no raster dependency in the dashboard)."""
    try:
        import qrcode
        import qrcode.image.svg

        image = qrcode.make(url, image_factory=qrcode.image.svg.SvgImage, box_size=10, border=2)
        buffer = io.BytesIO()
        image.save(buffer)
        return buffer.getvalue().decode("utf-8")
    except Exception as exc:  # pragma: no cover - qrcode is a hard dependency
        logger.warning("QR generation failed: %s", exc)
        return ""


def whatsapp_url(phone: str | None, url: str, reference: str) -> str:
    """``https://wa.me/<digits>?text=<urlencoded English message>``."""
    digits = re.sub(r"\D", "", phone or "")
    message = (
        f"Araxys Desk: your crop damage claim {reference} has been recorded. "
        f"Please upload your photos and documents here: {url} "
        "The link works for 7 days. Reply to this message if you need help."
    )
    encoded = quote(message, safe="")
    return f"https://wa.me/{digits}?text={encoded}" if digits else f"https://wa.me/?text={encoded}"


def create_link(claim_id: int) -> EvidenceLinkResponse:
    """Mint (or refresh) an upload link for a claim."""
    with session_scope() as session:
        claim = session.get(ClaimRow, claim_id)
        if claim is None:
            raise EvidenceError(f"claim {claim_id} not found")
        token = secrets.token_urlsafe(24)
        expires_at = _expiry()
        session.add(
            EvidenceTokenRow(
                token=token,
                claim_id=claim_id,
                created_at=now_iso(),
                expires_at=expires_at,
                revoked=False,
            )
        )
        reference = claim.reference
        phone = (claim.farmer or {}).get("phone")

    url = evidence_url(token)
    logger.info("evidence link created for claim %s (%s)", claim_id, reference)
    return EvidenceLinkResponse(
        token=token,
        url=url,
        qr_svg=build_qr_svg(url),
        whatsapp_url=whatsapp_url(phone, url, reference),
        expires_at=expires_at,
    )


def resolve_token(token: str) -> tuple[EvidenceTokenRow, ClaimRow]:
    """Validate a token and return its row plus the claim. Raises on failure."""
    with read_session() as session:
        row = session.get(EvidenceTokenRow, token)
        if row is None or row.revoked:
            raise EvidenceError("This upload link is not valid.")
        try:
            expires = datetime.fromisoformat(row.expires_at)
        except ValueError:
            expires = datetime.now(timezone.utc)
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires < datetime.now(timezone.utc):
            raise EvidenceError("This upload link has expired.")
        claim = session.get(ClaimRow, row.claim_id)
        if claim is None:
            raise EvidenceError("The claim for this link no longer exists.")
        session.expunge(row)
        session.expunge(claim)
        return row, claim


# --------------------------------------------------------------------------
# checklist translation
# --------------------------------------------------------------------------
def _cache_key(items: list[EvidenceItem], language: str) -> str:
    payload = json.dumps(
        [[item.key, item.label, item.why] for item in items], sort_keys=True, ensure_ascii=False
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"translation:{language}:{digest}"


async def translate_checklist(
    items: list[EvidenceItem], language: str
) -> dict[str, tuple[str, str]]:
    """``{key: (label_local, instructions_local)}``; English passthrough on failure."""
    english = {
        item.key: (
            item.label,
            item.why or f"Please upload: {item.label}.",
        )
        for item in items
    }
    language = (language or "en").split("-")[0].lower()
    if language == "en" or not items:
        return english

    cache_key = _cache_key(items, language)
    cached = meta_get(cache_key)
    if isinstance(cached, dict) and cached:
        return {
            key: (value.get("label_local") or english.get(key, ("", ""))[0],
                  value.get("instructions_local") or english.get(key, ("", ""))[1])
            for key, value in cached.items()
        }

    from services import gemini

    if not gemini.is_available():
        return english

    language_name = LANGUAGE_NAMES.get(language, language)
    listing = "\n".join(
        f"- key: {item.key}\n  label: {item.label}\n  why: {item.why or ''}" for item in items
    )
    prompt = (
        f"Translate this crop-insurance document checklist into {language_name} for a "
        "farmer with limited literacy who will read it on a phone.\n\n"
        "For each item return:\n"
        "- label_local: the document name, 2-5 words, the words a villager actually uses.\n"
        "- instructions_local: one short sentence telling them what to photograph and "
        "how (daylight, whole document in frame, the damaged area visible).\n\n"
        "Keep every key exactly as given. Do not add items. Do not mention money, "
        "approval, or any timeline.\n\n"
        f"Items:\n{listing}"
    )

    result = await gemini.generate_json(prompt, TranslationResult)
    if result is None:
        return english

    translated: dict[str, tuple[str, str]] = {}
    payload: dict[str, dict[str, str]] = {}
    for entry in result.items:
        if entry.key not in english:
            continue
        label = entry.label_local.strip() or english[entry.key][0]
        instructions = entry.instructions_local.strip() or english[entry.key][1]
        translated[entry.key] = (label, instructions)
        payload[entry.key] = {"label_local": label, "instructions_local": instructions}

    for key, value in english.items():
        translated.setdefault(key, value)

    if payload:
        meta_set(cache_key, payload)
        logger.info("cached %s checklist translations for %s", len(payload), language)
    return translated


async def build_page(token: str) -> EvidencePage:
    """The farmer-facing checklist for one token."""
    token_row, claim = resolve_token(token)
    items = coerce_list(EvidenceItem, claim.evidence_required or [])
    language = (claim.farmer or {}).get("language") or "en"
    translations = await translate_checklist(items, language)

    with read_session() as session:
        uploads = load_evidence_files(session, claim.id)

    by_key: dict[str, list[EvidenceFile]] = {}
    for upload in uploads:
        by_key.setdefault(upload.item_key, []).append(upload)

    page_items: list[EvidenceChecklistItem] = []
    for item in items:
        label_local, instructions_local = translations.get(
            item.key, (item.label, item.why or "")
        )
        page_items.append(
            EvidenceChecklistItem(
                key=item.key,
                label=item.label,
                label_local=label_local,
                instructions_local=instructions_local,
                required=item.required,
                uploaded=by_key.get(item.key, []),
            )
        )

    return EvidencePage(
        claim_reference=claim.reference,
        farmer_language=language,
        items=page_items,
        expires_at=token_row.expires_at,
    )


# --------------------------------------------------------------------------
# uploads
# --------------------------------------------------------------------------
def _extension(filename: str, content_type: str) -> str:
    mapped = ALLOWED_CONTENT_TYPES.get((content_type or "").lower())
    if mapped:
        return mapped
    suffix = Path(filename or "").suffix.lower()
    if suffix in set(ALLOWED_CONTENT_TYPES.values()):
        return suffix
    raise EvidenceError(
        "Only photos (JPG, PNG, WEBP, HEIC) and PDF files can be uploaded."
    )


def _to_degrees(value: Any) -> Optional[float]:
    try:
        degrees, minutes, seconds = (float(part) for part in value)
        return degrees + minutes / 60 + seconds / 3600
    except Exception:
        return None


def extract_exif(path: Path) -> dict[str, Any]:
    """Best-effort EXIF: capture time and GPS. Never raises."""
    info: dict[str, Any] = {}
    try:
        from PIL import ExifTags, Image

        with Image.open(path) as image:
            exif = image.getexif()
            if not exif:
                return info
            tags = {ExifTags.TAGS.get(tag, tag): value for tag, value in exif.items()}
            taken = tags.get("DateTimeOriginal") or tags.get("DateTime")
            if taken:
                info["taken_at"] = str(taken)

            gps_raw = exif.get_ifd(0x8825) if hasattr(exif, "get_ifd") else None
            if gps_raw:
                gps = {ExifTags.GPSTAGS.get(tag, tag): value for tag, value in gps_raw.items()}
                lat = _to_degrees(gps.get("GPSLatitude"))
                lon = _to_degrees(gps.get("GPSLongitude"))
                if lat is not None and str(gps.get("GPSLatitudeRef", "N")).upper() == "S":
                    lat = -lat
                if lon is not None and str(gps.get("GPSLongitudeRef", "E")).upper() == "W":
                    lon = -lon
                if lat is not None:
                    info["lat"] = round(lat, 6)
                if lon is not None:
                    info["lon"] = round(lon, 6)
    except Exception as exc:
        logger.debug("no EXIF read from %s: %s", path.name, exc.__class__.__name__)
    return info


async def save_upload(
    token: str,
    item_key: str,
    filename: str,
    content_type: str,
    data: bytes,
    client_time: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
) -> EvidenceFile:
    """Persist one uploaded file against the claim behind ``token``."""
    _, claim = resolve_token(token)

    if not data:
        raise EvidenceError("The file was empty.")
    if len(data) > settings.max_upload_bytes:
        limit_mb = settings.max_upload_bytes // (1024 * 1024)
        raise EvidenceError(f"That file is larger than {limit_mb} MB. Please send a smaller photo.")

    extension = _extension(filename, content_type)
    file_id = uuid.uuid4().hex
    directory = settings.evidence_dir / str(claim.id)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{file_id}{extension}"
    path.write_bytes(data)

    exif = extract_exif(path) if extension != ".pdf" else {}
    final_lat = lat if lat is not None else exif.get("lat")
    final_lon = lon if lon is not None else exif.get("lon")
    final_client_time = client_time or exif.get("taken_at")

    known_keys = {
        item.get("key") for item in (claim.evidence_required or []) if isinstance(item, dict)
    }
    resolved_key = item_key if item_key in known_keys else (item_key or "other")

    with session_scope() as session:
        row = EvidenceFileRow(
            id=file_id,
            claim_id=claim.id,
            item_key=resolved_key,
            filename=Path(filename or f"upload{extension}").name[:255],
            content_type=(content_type or "application/octet-stream")[:64],
            size=len(data),
            path=str(path),
            uploaded_at=now_iso(),
            client_time=final_client_time,
            lat=final_lat,
            lon=final_lon,
            quality_flag="unchecked",
            exif=exif,
        )
        session.add(row)
        session.flush()
        record = evidence_file_to_schema(row)

    await emit(
        "evidence.uploaded",
        {
            "claim_id": claim.id,
            "claim_reference": claim.reference,
            "file": record.model_dump(mode="json"),
        },
    )
    logger.info("evidence %s stored for claim %s (%s bytes)", file_id, claim.id, len(data))
    return record


def file_path_for(file_id: str) -> tuple[Path, str, str]:
    """(path, content_type, filename) for the binary endpoint."""
    with read_session() as session:
        row = session.get(EvidenceFileRow, file_id)
        if row is None:
            raise EvidenceError("File not found.")
        path = Path(row.path)
        if not path.exists():
            raise EvidenceError("File is no longer on disk.")
        return path, row.content_type or "application/octet-stream", row.filename


def files_for_claim(claim_id: int) -> list[EvidenceFile]:
    with read_session() as session:
        return load_evidence_files(session, claim_id)


def revoke_claim_tokens(claim_id: int) -> int:
    with session_scope() as session:
        rows = session.scalars(
            select(EvidenceTokenRow).where(EvidenceTokenRow.claim_id == claim_id)
        ).all()
        for row in rows:
            row.revoked = True
        return len(rows)
