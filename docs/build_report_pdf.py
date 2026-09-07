"""Builds docs/Araxys_Desk_Project_Report.pdf from the project's existing docs.

Run: backend/.venv/Scripts/python docs/build_report_pdf.py
(from the repo root). Content is derived only from README.md, PLAN.md and
docs/data-sources.md already in this repo -- no new facts are introduced.
"""
from __future__ import annotations

import os

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Image,
    ListFlowable,
    ListItem,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHOTS = os.path.join(ROOT, "dashboard", "docs", "screenshots")
OUT = os.path.join(ROOT, "docs", "Araxys_Desk_Project_Report.pdf")

INK = colors.HexColor("#1b2a22")
MUTED = colors.HexColor("#5b6a60")
ACCENT = colors.HexColor("#2f7a4f")
ACCENT_DARK = colors.HexColor("#1f5738")
LINE = colors.HexColor("#d8e2dc")
PANEL = colors.HexColor("#f2f6f3")

styles = getSampleStyleSheet()

title_style = ParagraphStyle(
    "TitleBig", parent=styles["Title"], fontName="Helvetica-Bold",
    fontSize=34, leading=38, textColor=INK, alignment=TA_CENTER, spaceAfter=6,
)
tagline_style = ParagraphStyle(
    "Tagline", parent=styles["Normal"], fontName="Helvetica-Oblique",
    fontSize=13, leading=18, textColor=MUTED, alignment=TA_CENTER, spaceAfter=4,
)
badge_style = ParagraphStyle(
    "Badge", parent=styles["Normal"], fontName="Helvetica-Bold",
    fontSize=12, leading=16, textColor=colors.white, alignment=TA_CENTER,
)
h1 = ParagraphStyle(
    "H1", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=18,
    leading=22, textColor=ACCENT_DARK, spaceBefore=18, spaceAfter=10,
    borderPadding=0,
)
h2 = ParagraphStyle(
    "H2", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=12.5,
    leading=16, textColor=INK, spaceBefore=12, spaceAfter=6,
)
body = ParagraphStyle(
    "Body", parent=styles["Normal"], fontName="Helvetica", fontSize=10,
    leading=15, textColor=INK, alignment=TA_LEFT, spaceAfter=6,
)
body_muted = ParagraphStyle(
    "BodyMuted", parent=body, textColor=MUTED, fontSize=9.3, leading=13.5,
)
li_style = ParagraphStyle(
    "LI", parent=body, spaceAfter=4,
)
cell = ParagraphStyle("Cell", parent=body, fontSize=9, leading=12.5, spaceAfter=0)
cell_head = ParagraphStyle(
    "CellHead", parent=cell, fontName="Helvetica-Bold", textColor=colors.white,
)
caption_style = ParagraphStyle(
    "Caption", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=10.5,
    leading=13, textColor=ACCENT_DARK, spaceBefore=10, spaceAfter=4,
)
footer_note = ParagraphStyle(
    "FooterNote", parent=body_muted, alignment=TA_CENTER, fontSize=8.3,
)


def P(text: str, style: ParagraphStyle = body) -> Paragraph:
    return Paragraph(text, style)


def bullets(items: list[str], style: ParagraphStyle = li_style) -> ListFlowable:
    return ListFlowable(
        [ListItem(P(t, style), bulletColor=ACCENT) for t in items],
        bulletType="bullet", start="circle", leftIndent=14, bulletFontSize=6.5,
        spaceBefore=2, spaceAfter=8,
    )


def section_rule(c, doc):
    c.saveState()
    c.setStrokeColor(LINE)
    c.setLineWidth(0.6)
    c.line(2 * cm, doc.pagesize[1] - 1.55 * cm, doc.pagesize[0] - 2 * cm, doc.pagesize[1] - 1.55 * cm)
    c.restoreState()


def on_page(c, doc):
    c.saveState()
    c.setFont("Helvetica", 8)
    c.setFillColor(MUTED)
    c.drawString(2 * cm, 1.15 * cm, "Araxys Desk — Voiceathon Round 2 Project Report")
    c.drawRightString(doc.pagesize[0] - 2 * cm, 1.15 * cm, f"Page {doc.page}")
    c.setStrokeColor(LINE)
    c.setLineWidth(0.6)
    c.line(2 * cm, 1.45 * cm, doc.pagesize[0] - 2 * cm, 1.45 * cm)
    c.restoreState()


def on_title_page(c, doc):
    c.saveState()
    c.setFillColor(ACCENT)
    c.rect(0, doc.pagesize[1] - 2.6 * cm, doc.pagesize[0], 2.6 * cm, stroke=0, fill=1)
    c.setFillColor(ACCENT_DARK)
    c.rect(0, 0, doc.pagesize[0], 1.4 * cm, stroke=0, fill=1)
    c.setFillColor(colors.white)
    c.setFont("Helvetica", 9)
    c.drawCentredString(doc.pagesize[0] / 2, 0.55 * cm, "Backend: FastAPI + Python  ·  Voice: SnapServe / Gemini Live  ·  Dashboard: React + Vite")
    c.restoreState()


doc = SimpleDocTemplate(
    OUT, pagesize=A4,
    topMargin=2.1 * cm, bottomMargin=2.0 * cm, leftMargin=2 * cm, rightMargin=2 * cm,
    title="Araxys Desk — Project Report", author="Kevin Sudhan",
    subject="Voiceathon Round 2 hackathon submission (3rd place)",
)

story: list = []

# ---------------------------------------------------------------- Title page
story.append(Spacer(1, 3.2 * cm))
story.append(P("Araxys Desk", title_style))
story.append(P("A voice-first crop-insurance claims desk for Indian farmers —", tagline_style))
story.append(P("grounded in real data, guarded against false promises, reachable in any language.", tagline_style))
story.append(Spacer(1, 0.5 * cm))

badge_tbl = Table(
    [[P("VOICEATHON ROUND 2  ·  VOICE AI FOR FARMER ADVISORY &amp; CROP-INSURANCE CLAIMS", badge_style)],
     [P("RESULT: 3RD PLACE", ParagraphStyle("BadgeBig", parent=badge_style, fontSize=15, spaceBefore=2))]],
    colWidths=[15.5 * cm],
)
badge_tbl.setStyle(TableStyle([
    ("BACKGROUND", (0, 0), (-1, -1), ACCENT_DARK),
    ("TOPPADDING", (0, 0), (-1, 0), 10), ("BOTTOMPADDING", (0, 0), (-1, 0), 4),
    ("TOPPADDING", (0, 1), (-1, 1), 4), ("BOTTOMPADDING", (0, 1), (-1, 1), 12),
    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
]))
story.append(badge_tbl)
story.append(Spacer(1, 1.3 * cm))

story.append(P(
    "Araxys Desk lets a farmer call a phone number, describe crop damage in their own language "
    "and dialect, and be walked through a PMFBY (Pradhan Mantri Fasal Bima Yojana) crop-insurance "
    "claim by an AI voice agent named <b>Sunil</b>. Every fact the agent speaks — weather, disaster "
    "records, scheme rules — is checked against real government and meteorological data and shown "
    "with a citation in a companion CRM dashboard built for reviewers and judges.",
    ParagraphStyle("LeadIn", parent=body, fontSize=11, leading=17, alignment=TA_CENTER,
                    textColor=INK, spaceAfter=0),
))
story.append(Spacer(1, 1.6 * cm))

meta_rows = [
    [P("Project", cell_head.clone("mh1", textColor=MUTED, fontName="Helvetica-Bold")), P("Araxys Desk (Voiceathon Round 2 build codename)", cell)],
    [P("Voice agent", cell_head.clone("mh2", textColor=MUTED, fontName="Helvetica-Bold")), P("“Sunil” on SnapServe, powered by Gemini Live (native speech-to-speech)", cell)],
    [P("Reviewer / judge surface", cell_head.clone("mh3", textColor=MUTED, fontName="Helvetica-Bold")), P("React + Vite CRM dashboard with a live truth-check and citations panel", cell)],
    [P("Author", cell_head.clone("mh4", textColor=MUTED, fontName="Helvetica-Bold")), P("Kevin Sudhan", cell)],
]
meta_tbl = Table(meta_rows, colWidths=[4.3 * cm, 11.2 * cm])
meta_tbl.setStyle(TableStyle([
    ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ("LINEBELOW", (0, 0), (-1, -2), 0.5, LINE),
]))
story.append(meta_tbl)
story.append(PageBreak())

# ---------------------------------------------------------------- The problem
story.append(P("The problem", h1))
story.append(P(
    "Crop-insurance claims in India are filed by phone, often in a farmer's second language, "
    "under stress, immediately after a weather event. Two things regularly go wrong:", body,
))
story.append(bullets([
    "<b>Overpromising.</b> A stressed farmer asks “will I get money, how much, when?” — and any "
    "agent (human or AI) that answers with a number, a guarantee, or an approval is committing the "
    "scheme to something it hasn't decided yet.",
    "<b>Ungrounded claims.</b> A caller may misremember a date, conflate one damage type with "
    "another, or (rarely) attempt fraud. Without checking the claim against real weather and "
    "disaster records, none of that gets caught before it reaches a reviewer.",
]))
story.append(P("Araxys Desk's whole design is a response to those two failure modes.", body))

# ---------------------------------------------------------------- What it does
story.append(P("What Araxys Desk does", h1))
story.append(bullets([
    "<b>Answers the call in whatever language the farmer speaks</b> (Gemini Live native "
    "speech-to-speech, roughly 97 languages, follows code-switching mid-call) and walks through a "
    "structured intake — crop, land extent, damage type, event date, location — confirming each "
    "step back to the caller.",
    "<b>Truth-checks the story.</b> For a claimed event (“a cyclone on 12 September”), the backend "
    "checks real weather records (Open-Meteo) and disaster alerts (GDACS) for that place and date "
    "and reports a plausibility verdict — <i>supported</i>, <i>partially_supported</i>, "
    "<i>not_supported</i>, or <i>unverifiable</i> — never invented.",
    "<b>Explains the scheme accurately.</b> Every scheme fact the agent may say — coverage, "
    "documents needed, the 72-hour intimation window, the helpline — comes from a curated fact "
    "base built from the official PMFBY Operational Guidelines PDF, cited by page and paragraph, "
    "never guessed.",
    "<b>Never states a payout.</b> Money, approval, and timeline questions are answered with "
    "pre-approved, guardrailed scripts — process, not outcome.",
    "<b>Logs or escalates.</b> Claims that pass validation are logged with a reference number; "
    "anything ambiguous, mismatched, high-risk, or where the farmer asks for a human is escalated "
    "to a reviewer with a plain-language, non-accusatory reason.",
    "<b>Sends an evidence-upload link</b> (WhatsApp / SMS) so the farmer can photograph the "
    "required documents from their phone, with a live checklist in their own language.",
    "<b>Shows all of this to a reviewer / judge</b> in a live CRM dashboard — transcript, "
    "truth-check panel with citations, claims table, tickets, a Tamil Nadu district map, and a "
    "guardrail-incident scoreboard.",
]))

# ---------------------------------------------------------------- Architecture
story.append(P("Architecture", h1))
story.append(P(
    "A farmer calls the assigned Vobiz DID, or a judge opens a SnapServe webcall link. Either way "
    "the call is handled by the SnapServe voice runtime running Gemini Live in native-audio mode, "
    "which follows the caller into whatever language they use. The backend (FastAPI, Python) does "
    "not depend on mid-call tool calls — early testing showed SnapServe's mid-call webhook tool "
    "calling to be unreliable — so instead a 60-day weather / disaster snapshot for all 38 Tamil "
    "Nadu districts (pulled once from Open-Meteo and GDACS), plus the scheme facts, crop calendar, "
    "evidence checklists and safe scripts, are all rendered directly into the agent's system "
    "prompt ahead of time.", body,
))
story.append(P(
    "After the call ends, the backend polls SnapServe's calls API for the completed transcript — "
    "no public tunnel or inbound webhook is required. An ingest pipeline re-derives the same "
    "truth-check from the snapshot, runs a risk score, and attaches real citations to every fact "
    "the agent spoke. The result is stored in SQLite (calls, claims, tickets, evidence, citations, "
    "guardrail incidents) and pushed live to the React dashboard over a WebSocket event bus.", body,
))

arch_data = [
    [P("Layer", cell_head), P("Component", cell_head), P("Role", cell_head)],
    [P("Voice", cell), P("SnapServe + Gemini Live", cell), P("Native speech-to-speech phone / webcall agent (“Sunil”)", cell)],
    [P("Backend", cell), P("FastAPI (Python)", cell), P("Polls SnapServe, runs ingest + truth-check + guardrail pipeline, serves the API/WebSocket", cell)],
    [P("Services", cell), P("weather · disasters · gazetteer · crops · schemes · guardrail · knowledge", cell), P("Domain logic reading from the pre-fetched snapshot and curated fact base", cell)],
    [P("Storage", cell), P("SQLite", cell), P("Calls, claims, tickets, evidence, citations, guardrail incidents", cell)],
    [P("Dashboard", cell), P("React + Vite + Tailwind", cell), P("CRM / judge view: live calls, claims with citations, tickets, district map, guardrail scoreboard", cell)],
]
arch_tbl = Table(arch_data, colWidths=[2.5 * cm, 5.2 * cm, 7.8 * cm], repeatRows=1)
arch_tbl.setStyle(TableStyle([
    ("BACKGROUND", (0, 0), (-1, 0), ACCENT_DARK),
    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PANEL]),
    ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ("GRID", (0, 0), (-1, -1), 0.4, LINE),
]))
story.append(arch_tbl)
story.append(PageBreak())

# ---------------------------------------------------------------- Guardrails
story.append(P("Guardrails — why the agent can't overpromise", h1))
story.append(P(
    "Native speech-to-speech means there is no way to filter a sentence before it is spoken, so "
    "the guardrail strategy is layered instead of a single filter:", body,
))
guard_data = [
    [P("Layer", cell_head), P("What it does", cell_head)],
    [P("System prompt", cell), P("Explicit scope, banned commitments, “money / approval / timeline "
        "→ use the safe script”, “scheme facts → cite only what's in the knowledge base”, "
        "language mirroring, plain-language register.", cell)],
    [P("Safe scripts", cell), P("Canonical, pre-approved answers (in every supported language) for "
        "“will I get money”, “is it approved”, “when” — the agent reads these verbatim "
        "instead of improvising.", cell)],
    [P("Risk scoring", cell), P("Weather verdict, transcript contradictions, oversized land claims, "
        "out-of-season crops, and distress / “I want a human” signals all feed a risk score that "
        "decides logged vs. escalated.", cell)],
    [P("Post-call audit", cell), P("Every completed call is re-scanned by a rules-based multilingual "
        "detector plus a Gemini judge for promise leaks, fabricated scheme facts, and missed "
        "escalations — violations become a red guardrail incident and roll up into a scoreboard.", cell)],
    [P("Explainable escalation", cell), P("When a claim is escalated, the farmer is told why in "
        "plain, non-accusatory language (e.g. “the rain record for that day doesn't match what you "
        "described, so a person will check it with you”) — the same reason is attached to the "
        "reviewer's ticket.", cell)],
]
guard_tbl = Table(guard_data, colWidths=[3.3 * cm, 12.2 * cm], repeatRows=1)
guard_tbl.setStyle(TableStyle([
    ("BACKGROUND", (0, 0), (-1, 0), ACCENT_DARK),
    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PANEL]),
    ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ("GRID", (0, 0), (-1, -1), 0.4, LINE),
]))
story.append(guard_tbl)
story.append(Spacer(1, 8))
story.append(P(
    "<b>Stated honestly:</b> native audio can still speak a sentence before any external check "
    "runs. The mitigation is scripted answers on every sensitive turn plus a 100%-of-calls "
    "post-call audit, not a claim that nothing can ever slip through.", body_muted,
))

# ---------------------------------------------------------------- Data sources
story.append(P("Data sources &amp; citations", h1))
story.append(P(
    "Nothing the agent says about money, weather, or scheme rules is invented. Scheme facts (80+ "
    "of them) were extracted from the official PMFBY Revamped Operational Guidelines PDF, a PIB "
    "press release for the national helpline, the RWBCIS guidelines, and Tamil Nadu Kharif 2026 "
    "press coverage. Every fact carries a source URL, a page / paragraph reference, a retrieval "
    "date, and a verbatim quote of at most twenty-five words — verified automatically against the "
    "extracted source-PDF text, so a stale or incorrect quote fails the project's test suite rather "
    "than shipping silently.", body,
))
story.append(P(
    "Weather and disaster grounding comes from a 60-day snapshot for all 38 Tamil Nadu districts, "
    "pulled once from the free Open-Meteo forecast / archive API and the GDACS global disaster "
    "alert feed, cached to a JSON snapshot file and refreshed on demand — never fetched live "
    "mid-call, which keeps the voice agent's runtime independent of network calls during a "
    "conversation.", body,
))
story.append(P("Known gaps are stated, not guessed:", h2))
story.append(bullets([
    "Sum insured per hectare, indemnity level, and exact per-crop enrolment cut-off dates for the "
    "demo districts were not available from an official, quotable Tamil Nadu Kharif 2026 "
    "notification at build time.",
    "<i>lookup_scheme</i> returns these as explicit “unknown — a reviewer will confirm” facts "
    "instead of fabricating numbers.",
    "A clearly-labelled <b>simulated</b> sum-insured table is used only to demonstrate the "
    "“policy ceiling, not a payout” explanation flow, and is never presented as an official figure.",
]))
story.append(P(
    "The complete source list, extraction method, and refresh procedure are documented in "
    "<i>docs/data-sources.md</i> in the repository.", body_muted,
))

# ---------------------------------------------------------------- Tech stack
story.append(P("Tech stack", h1))
stack_data = [
    [P("Backend", cell_head), P("Python, FastAPI, SQLAlchemy + SQLite, Pydantic v2, google-genai (Gemini), httpx, WebSockets, pytest", cell)],
    [P("Voice", cell_head), P("SnapServe running Gemini Live (native speech-to-speech) for the phone / webcall agent", cell)],
    [P("LLM", cell_head), P("Google Gemini — gemini-3.6-flash for text tasks (extraction, guardrail judging); gemini-3.1-flash-live-preview for the live voice agent", cell)],
    [P("Dashboard", cell_head), P("React 18, TypeScript, Vite, Tailwind CSS 4, Radix UI, TanStack Query, Recharts, Framer Motion, Zustand, d3-geo (Tamil Nadu district map)", cell)],
    [P("Real-world data", cell_head), P("Open-Meteo (weather), GDACS (disasters), PMFBY Operational Guidelines + Tamil Nadu notifications (scheme facts), data.gov.in (crop production stats)", cell)],
]
stack_tbl = Table(stack_data, colWidths=[3.3 * cm, 12.2 * cm], repeatRows=0)
stack_tbl.setStyle(TableStyle([
    ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, PANEL]),
    ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ("GRID", (0, 0), (-1, -1), 0.4, LINE),
]))
story.append(stack_tbl)

# ---------------------------------------------------------------- Limitations
story.append(P("Known limitations", h1))
story.append(P("Stated openly, matching the project's own “never fabricate, mark unverifiable” principle:", body))
story.append(bullets([
    "Native speech-to-speech can speak a sentence before any external filter runs — mitigated by "
    "scripted answers on sensitive turns plus 100% post-call audit, not eliminated.",
    "Sum insured, indemnity level, and exact per-crop cut-off dates for the demo districts were not "
    "available from an official, quotable Tamil Nadu Kharif 2026 notification at build time; the "
    "agent states these as unknown rather than guessing.",
    "Weather / disaster data is a point-in-time snapshot (refreshed on demand, not live-streamed) "
    "by design, to keep the voice agent's runtime independent of network calls during a call.",
    "Built and demoed for Tamil Nadu districts; extending to other states means adding their "
    "notifications and gazetteer data.",
]))
story.append(PageBreak())

# ---------------------------------------------------------------- Screenshots
story.append(P("Dashboard screenshots", h1))
story.append(P(
    "The CRM / judge dashboard renders the truth-check and citations behind every claim in real "
    "time. A selection of views follows.", body,
))

shot_specs = [
    ("01-overview.png", "Overview — live stats, verdict mix, and recent activity."),
    ("04-claim-detail.png", "Claim detail — truth panel with weather chart, disaster events, scheme "
        "facts and citation chips, risk gauge, transcript, and evidence gallery."),
    ("07-knowledge-map.png", "Knowledge — Tamil Nadu district map coloured by recent rainfall, with "
        "snapshot status and source list."),
    ("08-guardrails.png", "Guardrails — incident log and scoreboard from the post-call audit."),
]

max_w = 15.5 * cm
max_h_first = 20.0 * cm

for i, (fname, caption) in enumerate(shot_specs):
    path = os.path.join(SHOTS, fname)
    if not os.path.exists(path):
        continue
    from PIL import Image as PILImage
    with PILImage.open(path) as im:
        iw, ih = im.size
    scale = max_w / iw
    draw_w, draw_h = max_w, ih * scale
    max_h = max_h_first if i == 0 else 21.5 * cm
    if draw_h > max_h:
        scale = max_h / ih
        draw_w, draw_h = iw * scale, max_h
    if i > 0:
        story.append(PageBreak())
        story.append(P("Dashboard screenshots (continued)", h1))
    story.append(P(caption, caption_style))
    story.append(Image(path, width=draw_w, height=draw_h))

story.append(PageBreak())
story.append(Spacer(1, 8 * cm))
story.append(P(
    "Built for Voiceathon Round 2 — Voice AI for Farmer Advisory &amp; Crop-Insurance Claims. "
    "3rd place.", footer_note,
))
story.append(P(
    "Full source, documentation, and test suite: "
    "github.com/kevinsudhan/snapserve-hackathon-final", footer_note,
))

doc.build(story, onFirstPage=on_title_page, onLaterPages=lambda c, d: (on_page(c, d), section_rule(c, d)))
print("Wrote", OUT)
