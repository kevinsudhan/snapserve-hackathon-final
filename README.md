# Araxys Desk — Voiceathon Round 2 🏆 3rd Place

**A voice-first crop-insurance claims desk for Indian farmers — grounded in real data, guarded against false promises, and reachable by phone in any language.**

Araxys Desk lets a farmer call a phone number, describe crop damage in their own language and dialect, and be walked through a PMFBY (Pradhan Mantri Fasal Bima Yojana) crop-insurance claim by an AI voice agent named **Sunil**. Every fact the agent speaks — weather, disaster records, scheme rules — is checked against real government/meteorological data and shown with a citation in a companion CRM dashboard built for reviewers and judges.

Built for **Voiceathon Round 2**, placed **3rd** in the hackathon.

---

## Table of contents

- [The problem](#the-problem)
- [What Araxys Desk does](#what-araxys-desk-does)
- [Architecture](#architecture)
- [Guardrails — why the agent can't overpromise](#guardrails--why-the-agent-cant-overpromise)
- [Data & citations](#data--citations)
- [Repository layout](#repository-layout)
- [Tech stack](#tech-stack)
- [Screenshots](#screenshots)
- [Running it locally](#running-it-locally)
- [Backend API summary](#backend-api-summary)
- [Known limitations](#known-limitations)
- [Documentation index](#documentation-index)

---

## The problem

Crop-insurance claims in India are filed by phone, often in a farmer's second language, under stress, immediately after a weather event. Two things regularly go wrong:

1. **Overpromising.** A stressed farmer asks "will I get money, how much, when?" — and any agent (human or AI) that answers with a number, a guarantee, or an approval is committing the scheme to something it hasn't decided yet.
2. **Ungrounded claims.** A caller may misremember a date, conflate one damage type with another, or (rarely) attempt fraud. Without checking the claim against real weather and disaster records, none of that gets caught before it reaches a reviewer.

Araxys Desk's whole design is a response to those two failure modes.

## What Araxys Desk does

1. **Answers the call in whatever language the farmer speaks** (Gemini Live native speech-to-speech, ~97 languages, follows code-switching mid-call) and walks through a structured intake: crop → land extent → damage type → event date → location, confirming each step back to the caller.
2. **Truth-checks the story.** For a claimed event ("a cyclone on 12 September"), the backend checks real weather records (Open-Meteo) and disaster alerts (GDACS) for that place and date and reports a plausibility verdict — `supported`, `partially_supported`, `not_supported`, or `unverifiable` (never invented).
3. **Explains the scheme accurately.** Every scheme fact the agent may say (coverage, documents needed, the 72-hour intimation window, the helpline) comes from a curated fact base built from the official PMFBY Operational Guidelines PDF, cited by page and paragraph — never guessed.
4. **Never states a payout.** Money, approval, and timeline questions are answered with pre-approved, guardrailed scripts — process, not outcome. See [Guardrails](#guardrails--why-the-agent-cant-overpromise).
5. **Logs or escalates.** Claims that pass validation are logged with a reference number; anything ambiguous, mismatched, high-risk, or where the farmer asks for a human is escalated to a reviewer with a plain-language, non-accusatory reason.
6. **Sends an evidence-upload link** (WhatsApp/SMS) so the farmer can photograph the required documents from their phone, with a live checklist in their own language.
7. **Shows all of this to a reviewer/judge in a live CRM dashboard** — transcript, truth-check panel with citations, claims table, tickets, a Tamil Nadu district map, and a guardrail-incident scoreboard.

## Architecture

```
 Farmer phone ──Vobiz DID +91 79658 54267──┐
 Judge browser ──SnapServe webcall link ───┤
                                           ▼
                SnapServe voice runtime  (Gemini Live 3.1, native audio, any language)
                 │  (no mid-call tool calls — see note below)   │ call.completed webhook / polling
                 ▼                                               ▼
     ┌──────────────────────────  BACKEND (FastAPI, Python)  ───────────────────────────────┐
     │  Polls SnapServe for completed calls (GET /api/calls) — no public tunnel needed       │
     │  Ingest pipeline: transcript → Gemini extraction → truth-check → risk score → claim   │
     │  services/  weather · disasters · gazetteer · crops · schemes · guardrail · knowledge │
     │  SQLite: calls, claims, tickets, evidence, citations, guardrail incidents             │
     │  WebSocket event bus → dashboard                                                      │
     └──────────────────────────────────────────────────────────────────────────────────────┘
                                           │
                                           ▼
     CRM / Judge dashboard (React + Vite + Tailwind): Live call · Claims with citations ·
     Tickets · Knowledge / district map · Guardrails scoreboard · Mobile evidence-upload page
```

**Design note — no mid-call tool calls.** Early testing showed SnapServe's mid-call webhook tool calling to be unreliable, so Araxys Desk does not depend on it. Instead, a 60-day weather/disaster snapshot (all 38 Tamil Nadu districts, pulled once from Open-Meteo + GDACS) plus the scheme facts, crop calendar, evidence checklists, and safe scripts are all rendered into the agent's **system prompt** ahead of time. The backend never needs to be publicly reachable during a call — it simply polls SnapServe's calls API afterwards, re-derives the same truth-check from the snapshot, and attaches real citations to everything the agent said.

## Guardrails — why the agent can't overpromise

Native speech-to-speech means there's no way to filter a sentence before it's spoken, so the guardrail strategy is layered instead of a single filter:

| Layer | What it does |
|---|---|
| **System prompt** | Explicit scope, banned commitments, "money/approval/timeline → use the safe script", "scheme facts → cite only what's in the knowledge base", language mirroring, plain-language register. |
| **Safe scripts** | Canonical, pre-approved answers (in every supported language) for "will I get money", "is it approved", "when" — the agent reads these verbatim instead of improvising. |
| **Risk scoring** | Weather verdict, transcript contradictions, oversized land claims, out-of-season crops, and distress/"I want a human" signals all feed a risk score that decides `logged` vs `escalated`. |
| **Post-call audit** | Every completed call is re-scanned by a rules-based multilingual detector plus a Gemini judge for promise leaks, fabricated scheme facts, and missed escalations — violations become a red guardrail incident on the CRM record and roll up into a scoreboard. |
| **Escalation is explainable** | When a claim is escalated, the farmer is told why in plain, non-accusatory language ("the rain record for that day doesn't match what you described, so a person will check it with you") — the same reason is attached to the reviewer's ticket. |

The one honestly-stated limitation: native audio *can* speak a sentence before any external check runs. The mitigation is scripted answers on every sensitive turn plus 100%-of-calls post-call audit, not a promise that nothing can ever slip through.

## Data & citations

Nothing the agent says about money, weather, or scheme rules is invented:

- **Scheme facts** — 80+ facts extracted from the official [PMFBY Revamped Operational Guidelines](https://pmfby.gov.in/pdf/Revamped%20OGs_Final.pdf), a PIB press release (helpline), the RWBCIS guidelines, and Tamil Nadu Kharif 2026 press coverage. Every fact carries a source URL, page/paragraph, retrieval date, and a verbatim quote — verified automatically against the source PDF text so a stale quote fails the test suite. Full source list: [docs/data-sources.md](docs/data-sources.md).
- **Weather & disaster truth-check** — a 60-day snapshot for all 38 Tamil Nadu districts, pulled once from the free [Open-Meteo](https://open-meteo.com/) forecast/archive API and [GDACS](https://www.gdacs.org/) global disaster alerts, cached to `backend/data/weather_snapshot.json` and refreshed on demand (`POST /api/knowledge/refresh`) — never fetched live mid-call.
- **Known gaps are stated, not guessed.** Sum insured per hectare, indemnity levels, and exact per-crop enrolment cut-offs for the relevant districts were not published anywhere in quotable form at build time; `lookup_scheme` returns these as explicit "unknown, a reviewer will confirm" facts rather than fabricating numbers. A **simulated** sum-insured table (clearly labelled as simulated, `docs/knowledge/5_sum_insured_simulated.txt`) is used only to demonstrate the "policy ceiling, not a payout" explanation flow — see [docs/data-sources.md](docs/data-sources.md#known-gaps--deliberately-left-out-rather-than-guessed) for the complete list of what was deliberately left out.

## Repository layout

```
final/
  backend/            FastAPI app, services, prompts, data, tests
    app/              routers (calls, claims, tickets, evidence, knowledge, admin, ws, health)
    services/         weather, disasters, gazetteer, crops, schemes, guardrail, knowledge, ingest
    prompts/          system prompt template + rendered knowledge sections
    data/             schemes.json, crop_calendar_tn.json, weather_snapshot.json, sources/, evidence/
    scripts/          dev launcher, knowledge-refresh CLI, SnapServe agent sync
    tests/            pytest suite (core API, data services, guardrail, schemes verbatim-check)
  dashboard/          React + Vite + Tailwind CRM/judge dashboard
    src/pages/        Overview, LiveDesk, Claims, ClaimDetail, Tickets, Knowledge, Guardrails, Evidence
    docs/screenshots/ dashboard screenshots (see below)
  docs/
    CONTRACTS.md      binding API/data contracts every module was built against
    data-sources.md   full citation list, extraction method, refresh procedure
    knowledge/        the exact text baked into the agent's knowledge base
  PLAN.md             the original build plan (architecture, rubric strategy, phases)
  .env.example        required environment variables (no secrets)
```

## Tech stack

- **Backend:** Python, FastAPI, SQLAlchemy + SQLite, Pydantic v2, `google-genai` (Gemini), `httpx`, WebSockets, `pytest`.
- **Voice:** [SnapServe](https://app.snapserve.ai) running Gemini Live (native speech-to-speech) for the phone/webcall agent.
- **LLM:** Google Gemini (`gemini-3.6-flash` for text tasks — extraction, guardrail judging; `gemini-3.1-flash-live-preview` for the live voice agent).
- **Dashboard:** React 18, TypeScript, Vite, Tailwind CSS 4, Radix UI, TanStack Query, Recharts, Framer Motion, Zustand, `d3-geo` (Tamil Nadu district map).
- **Real-world data:** Open-Meteo (weather), GDACS (disasters), PMFBY Operational Guidelines + Tamil Nadu notifications (scheme facts), data.gov.in (crop production stats).

## Screenshots

| | |
|---|---|
| **Overview** | ![Overview](dashboard/docs/screenshots/01-overview.png) |
| **Live Desk** | ![Live Desk](dashboard/docs/screenshots/02-live-desk.png) |
| **Live Desk (full)** | ![Live Desk full](dashboard/docs/screenshots/03-live-desk-full.png) |
| **Claim detail — truth panel & citations** | ![Claim detail](dashboard/docs/screenshots/04-claim-detail.png) |
| **Claims table** | ![Claims table](dashboard/docs/screenshots/05-claims-table.png) |
| **Tickets** | ![Tickets](dashboard/docs/screenshots/06-tickets.png) |
| **Knowledge / district map** | ![Knowledge map](dashboard/docs/screenshots/07-knowledge-map.png) |
| **Guardrails scoreboard** | ![Guardrails](dashboard/docs/screenshots/08-guardrails.png) |
| **Evidence upload (mobile)** | ![Evidence mobile](dashboard/docs/screenshots/09-evidence-mobile.png) |
| **Overview (light theme)** | ![Overview light](dashboard/docs/screenshots/10-overview-light.png) |

## Running it locally

Prerequisites: Python 3.11+, Node 18+, a SnapServe account/API key, a Google Gemini API key.

```bash
# 1. Configure environment
cp .env.example .env
# fill in SNAPSERVE_API_KEY, GOOGLE_API_KEY, etc.

# 2. Backend
cd backend
python -m venv .venv
.venv/Scripts/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn app.main:app --port 8000 --reload

# 3. Dashboard (new terminal)
cd dashboard
npm install
npm run dev                 # or: npm run dev:mock — full UI on mock data, no backend needed
```

The dashboard dev server proxies `/api` and `/ws` to `http://localhost:8000`. See [docs/CONTRACTS.md](docs/CONTRACTS.md) for every environment variable and the full API contract.

## Backend API summary

The full typed contract (every endpoint, WebSocket event, and data shape) lives in [docs/CONTRACTS.md](docs/CONTRACTS.md). Highlights:

- `GET /api/health`, `/api/stats` — service and demo status.
- `GET /api/calls`, `/api/calls/{id}` — call records with transcripts and guardrail incidents.
- `GET /api/claims`, `/api/claims/{id}`, `PATCH /api/claims/{id}` — claims with weather/disaster/scheme evidence and citations.
- `GET /api/tickets`, `PATCH /api/tickets/{id}` — escalations for reviewers.
- `POST /api/claims/{id}/evidence-link`, `GET /api/evidence/{token}`, `POST /api/evidence/{token}/upload` — the mobile evidence-upload flow.
- `GET /api/knowledge/status`, `POST /api/knowledge/refresh` — the weather/scheme snapshot that's baked into the agent's prompt.
- `POST /api/admin/simulate` — replay a text transcript through the full ingest pipeline (used for demos and tests without a live call).
- `WS /ws/events` — live event stream that drives the dashboard.

## Known limitations

Stated openly, matching the project's own "never fabricate, mark unverifiable" principle:

- Native speech-to-speech can speak a sentence before any external filter runs — mitigated by scripted answers on sensitive turns plus 100% post-call audit, not eliminated.
- Sum insured, indemnity level, and exact per-crop cut-off dates for the demo districts were not available from an official, quotable Tamil Nadu Kharif 2026 notification at build time; the agent states these as unknown rather than guessing (see [docs/data-sources.md](docs/data-sources.md)).
- Weather/disaster data is a point-in-time snapshot (refreshed on demand, not live-streamed) by design, to keep the voice agent's runtime independent of network calls during a call.
- Built and demoed for Tamil Nadu districts; extending to other states means adding their notifications and gazetteer data.

## Documentation index

- [PLAN.md](PLAN.md) — the original build plan: rubric strategy, architecture, conversation design, phased build order.
- [docs/CONTRACTS.md](docs/CONTRACTS.md) — binding API endpoints, WebSocket events, and TypeScript/Pydantic data shapes.
- [docs/data-sources.md](docs/data-sources.md) — every scheme-fact source, extraction method, and refresh procedure.
- [docs/knowledge/](docs/knowledge/) — the exact scheme facts, evidence checklists, safe scripts, and weather record text baked into the voice agent's knowledge.

---

*Built for Voiceathon Round 2 — Voice AI for Farmer Advisory & Crop-Insurance Claims. 3rd place.*
