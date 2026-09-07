# Voiceathon Round 2 — Voice AI for Farmer Advisory & Crop-Insurance Claims
## Build plan v2 (orchestrator: Fable 5.1 · workers: Opus)

Status: BUILD IN PROGRESS (see docs/CONTRACTS.md for the binding v3 design).
> **v3 decisions (2026-09-05, Kevin):** the agent makes NO tool calls (SnapServe tool calling unreliable). Weather + disaster data for the past 60 days is pulled ONCE from Open-Meteo and GDACS into `backend/data/weather_snapshot.json` and baked into the agent's system prompt together with scheme facts, the crop calendar, evidence checklists and safe scripts. The CRM ingests completed calls by polling SnapServe (no tunnel), runs its own truth-check from the same snapshot, and links every citation to the real source page. Hosted locally on Kevin's laptop (HDMI). Number +91 79658 54267 is assigned to agent "Sunil" (id 1151); reviewer transfer number +91 89391 53390; Google key added to the SnapServe workspace. Evidence links are shown in the CRM (QR / copy / WhatsApp click-to-chat) rather than sent through SnapServe. Binding interfaces live in `docs/CONTRACTS.md`.


Hard requirements from Kevin (2026-09-05):
- Voice stack = **SnapServe** (app.snapserve.ai) running **Gemini Live** (native speech-to-speech).
- **Any language / dialect** the caller uses. No single-language limit anywhere, including backend LLM tasks.
- **Real data only** for schemes, crops, weather, disasters. Every fact carries a citation, and the CRM shows citations.
- **Weather truth-check**: "on 12 September a cyclone destroyed my crop" → agent queries a real weather API for that place and date and reports whether the data supports it.

---

## 0. Verified facts about the platforms (probed 2026-09-05, read-only)

SnapServe (key `sk_live_1cdf8d34…` works; base URL `https://app.snapserve.ai/api`, `Authorization: Bearer`):
- Agents are JSON objects: `systemPrompt`, `greetingMessage`, `firstSpeaker`, `llmProvider: "google"`, `llmModel: "gemini-3.1-flash-live-preview"`, `voiceStack: "gemini_live"`, `geminiLiveVoiceName` (30 preset voices, e.g. Kore, Charon, Achernar), `geminiLiveThinkingLevel`, `language`, a "follow the caller when they switch languages" flag, `temperature`, `maxDuration`, `silenceTimeoutSeconds`, `inactivityMessage`, `endCallPhrases`, `backchanneling*`, `noiseCancellationEnabled`, `recordingEnabled`, `dispositionSchema`, `webhookUrl`, `knowledgeSourceIds`.
- **Tools** on an agent: `webhook` (our HTTPS URL, GET/POST, headers, secret, JSON-schema `parameters`, `preToolMessage` spoken while the tool runs), `call_transfer` / `transfer_warm` (cold or warm with AI summary to the operator), `transfer_agent` (squad handoff), `end_call`, `send_sms`, `send_whatsapp`, `send_email`.
- **Post-call webhook endpoints**: event `call.completed` (and `call.failed`), HMAC-SHA256 `sha256=` signature, payload includes transcript, summary, disposition, callId.
- **Webcall links**: browser calling via `/api/agents/{id}/webcall-links` (share token → judge-facing demo link, no phone needed). Website embed snippet also available.
- **Phone**: workspace already owns Indian Vobiz DID **+91 79658 54267** (currently assigned to agent 717 "Priya", another project). Numbers can be re-assigned (`PATCH /api/phone-numbers/{id}/assign`) or a new one rented (₹799/month).
- **Outbound**: `POST /api/calls/outbound {agentId, toNumber}` → proactive calls. Destination OTP verification exists for non-KYC accounts.
- **Caller memory** per phone number (`/api/agents/{id}/caller-memory/{phone}`) — returning farmers are recognised.
- Provider keys: `POST /api/providers {providerType:"llm", providerName:"google", apiKey}` — "Live needs a Google API key on the workspace."
- Knowledge-base embeddings are broken in this workspace ("Embedding API key rejected") → we will NOT rely on SnapServe KB; scheme facts come from our tool.
- Gemini Live 3.1 = sequential function calling only (no async tools); ~97 languages; native audio auto-detects and follows language.

Google key (`AQ.…`, Vertex "express mode" format):
- Works on `generativelanguage.googleapis.com` — `gemini-3.6-flash` answered; `gemini-3.1-flash-live-preview` and `gemini-2.5-flash-native-audio-*` are listed as available.
- Vertex `aiplatform.googleapis.com` is DISABLED on project 538591521478 (403). If SnapServe routes Live through Vertex, Kevin must enable that API in the Google Cloud console. Verify in Phase 0.

Real data sources (all verified reachable):
- Open-Meteo Forecast API with `past_days` (last 92 days, daily rain / wind gusts / temp) and Archive API (any past date) — free, no key. Cyclone Gaja test (Nagapattinam 2018-11-16) returned 80.7 mm and 127 km/h gusts.
- GDACS event API (real global disaster alerts; returned a live Orange flood event in India, Aug–Sep 2026) with report URLs.
- PMFBY Revamped Operational Guidelines PDF (pmfby.gov.in/pdf/Revamped OGs_Final.pdf) — coverage, 72-hour intimation, premium shares, documents, helpline 14447.
- PMFBY district crop calendar PDF (pmfby.gov.in/pdf/New_Crop_Calendar_20.09.18.pdf) — district × crop × season sowing/harvest windows.
- Tamil Nadu Kharif 2026 notification: HDFC ERGO implementing in Cuddalore & Ranipet; notified crops list and cut-off dates (tnhorticulture.tn.gov.in/pmfby + press release).
- IMD district rainfall pages (mausam.imd.gov.in) — HTML, best-effort second source.
- data.gov.in district-wise crop production statistics (free API key) — "is this crop actually grown in this district" check.
- Open-Meteo Geocoding API + LGD/village lists — location resolution.

---

## 1. Rubric strategy (what gets 9–10 and avoids the disqualifiers)

| Criterion | Pts | Gating | Our answer |
|---|---|---|---|
| Guardrails vs overpromising | 20 | DQ | `say_safely` pre-speech guardrail tool + scripted-answer tool for money/approval/timeline questions + prompt + post-call auditor + red-team scoreboard |
| Language fidelity | 20 | – | Gemini Live native audio follows any language/dialect; prompt enforces short sentences, one question, confirm-before-advance, farmer register; tools return text in the caller's language |
| Data-grounded reasoning | 20 | DQ | Every claim triggers real Open-Meteo + GDACS queries; plausibility verdict with numbers; mismatch → gentle probe → escalate |
| Scheme accuracy | 15 | DQ | Facts only via `lookup_scheme`; each fact has source URL + as-of; agent states unknowns; grounding auditor |
| Escalation / fraud | 15 | DQ | Risk scorer inside `validate_claim`; `log_claim` refuses risky intakes; `escalate` creates ticket + optional warm transfer; distress / "human" → immediate |
| Conversation design | 10 | – | Gemini Live barge-in native; SnapServe silence timeout + inactivity message; slot state kept server-side so nothing restarts from zero |

---

## 2. Architecture

```
 Farmer phone ──Vobiz DID +91 79658 54267──┐
 Judge browser ──SnapServe webcall link ───┤
                                           ▼
                SnapServe voice runtime  (Gemini Live 3.1, native audio, any language)
                 │  function calls (sequential)            │ call.completed webhook (HMAC)
                 ▼                                         ▼
     ┌──────────────────────────  OUR BACKEND (FastAPI, Python)  ──────────────────────────┐
     │  /tools/*  (each = one SnapServe webhook tool)                                       │
     │   resolve_location · check_weather · check_disasters · lookup_scheme                 │
     │   validate_claim · log_claim · escalate · say_safely · answer_outcome_question       │
     │   remember (slot store)                                                              │
     │  /webhooks/snapserve  (post-call: transcript, summary → audit + CRM)                 │
     │  /admin/*  (data-down toggle, outbound trigger, red-team run)                        │
     │  WS event bus → dashboard                                                            │
     ├─ services ────────────────────────────────────────────────────────────────────────── │
     │  weather (Open-Meteo forecast+archive, IMD best-effort, cache, 2s timeout, down-mode)│
     │  disasters (GDACS), gazetteer (geocoding + LGD), crops (PMFBY calendar, data.gov.in) │
     │  schemes (curated JSON w/ citations from PMFBY OGs + TN notifications)               │
     │  claims/CRM (SQLite: calls, slots, claims, tickets, evidence, citations, audits)     │
     │  guardrail (deterministic multilingual validator + Gemini 3.6 Flash grounding judge) │
     └───────────────────────────────────────────────────────────────────────────────────────┘
                                           │
                                           ▼
            CRM / Judge dashboard (React): Live call grounding panel · Claims with citations ·
            Tickets · Red-team scoreboard · Controls (data-down, outbound call, language default)
```

Public HTTPS for the backend: cloudflared tunnel in dev; a small cloud VM/container (Fly.io / Render / Railway) for judging day. Tools authenticate SnapServe→us with the tool `secret` header; SnapServe API calls from us use the Bearer key from `.env`.

Repo layout:
```
final/
  backend/
    app/            # FastAPI: routers (tools, webhooks, admin, ws), models, settings
    services/       # weather, disasters, gazetteer, crops, schemes, claims, guardrail, snapserve_client
    prompts/        # system prompt (language-agnostic), safe scripts, tool descriptions
    data/           # schemes.json, crop_calendar.json, tn_notifications.json, gazetteer, disaster cache
    eval/           # red-team personas, runner (text-mode via Gemini), scorer, reports
    tests/
  snapserve/        # agent definition as JSON + script to create/update the agent, tools, webhooks
  dashboard/        # Vite + React + Tailwind
  docs/             # architecture.md (+diagram), guardrails.md, transcripts/, pitch.md, runbook.md, data-sources.md
  .env / .env.example
```

---

## 3. Conversation design (server-owned state, model-phrased turns)

Because Gemini Live holds the audio loop, our control comes from (a) the system prompt, (b) the tools it must call, (c) what those tools return. Slots live in our DB keyed by SnapServe callId, so an interrupted or resumed call never restarts.

Flow the prompt enforces (one question per turn, confirm before moving on):
1. Greet in the caller's language; ask why they're calling.
2. Collect: crop → land extent (acres/cents/hectares/bigha, normalised) → damage type → event date (relative dates like "last Tuesday", "Pongal-ku munnadi" resolved server-side) → village/taluk/district. After each slot: `remember(slot, value)` (keeps state server-side and lets the dashboard update live).
3. Read back a summary; get a yes.
4. `resolve_location` → `check_weather` + `check_disasters` → `validate_claim`. Speak the verdict gently: "The weather record for Cuddalore on 12 September shows 4 mm of rain and 29 km/h wind, which doesn't match a cyclone. Could the date be different?"
5. `lookup_scheme(crop, district, season, damage_type)` → explain only returned facts, say what's unknown.
6. Explain evidence: photos with date, land record (chitta/patta), sowing certificate, bank passbook, intimation within 72 hours via 14447 / Crop Insurance app / bank / insurer — from scheme facts only.
7. `log_claim` (only if validation passed) or `escalate` (ambiguous / mismatched / fraud signals / distress / human requested / data unavailable). Give the reference number.
7b. Explainable escalation to the farmer: `escalate` returns a non-accusatory, plain-language reason in the caller's language the agent must say (e.g., "the rain record for that day doesn't match what you described, so a person will check it with you"; "I couldn't reach the weather service, so a person will verify"; "you asked for a person"). The same reason, in full detail, goes on the ticket.
8. Any "will I get money / how much / when" at ANY point → `answer_outcome_question(question_type, language)` → read the returned script verbatim (process, not outcome).
9. Close with next steps; `end_call`.

Recovery rules in the prompt: if interrupted, answer the interruption then return to the pending slot; if the caller wanders, acknowledge, then one gentle steer; if upset, slow down, shorter sentences, offer a human; never repeat a question already answered (check `remember` state returned by tools).

---

## 4. Guardrail stack (redesigned for native audio — we cannot filter speech mid-turn)

1. **Prompt** — role, scope, banned commitments, "money/approval/timeline → tool", "scheme facts → tool only, cite", "unknown → say so", language mirroring, low-literacy register.
2. **`answer_outcome_question` tool** — returns the canonical safe script in the caller's language (generated by Gemini 3.6 Flash from an English template, validated by the deterministic filter, cached). The judge sees the tool fire on the grounding panel every time they bait.
3. **`say_safely(draft, category)` tool** — for eligibility/coverage/next-steps turns the prompt requires the model to submit its draft; the backend runs the multilingual deterministic validator (amounts, ₹/lakh, "approved", "guaranteed", "within N days", kandippa/nichayam/pakka/zaroor, loan/sell-land/medical/legal advice) plus a Gemini-Flash grounding check against the facts already returned in this call; returns `approved` or a corrected replacement to read. Adds ~0.3–0.6 s only on sensitive turns.
4. **Tool gates** — `log_claim` refuses without a passed `validate_claim`; risk ≥ threshold or `unverifiable` weather → must `escalate`; `escalate` is also triggered by server-side detection of distress/"human" phrases in tool inputs and transcripts.
5. **Post-call auditor** — on `call.completed`, the full transcript is scanned by the validator and a Gemini judge; violations create a red "guardrail incident" on the CRM record and feed the scoreboard. Zero incidents across the red-team runs is the headline number in the pitch.
6. **Red-team harness** — Gemini-simulated adversarial callers (many languages, baiting, contradicting, distressed, interrupting) drive the same tool backend through a text-mode replica of the Live prompt; scorer reports promise leaks, fabrications, missed escalations, one-question rate.

Known limitation to state honestly in guardrails.md: native speech-to-speech means a sentence can be spoken before any external filter; hence tools-for-sensitive-turns + post-call audit + prompt, and the eval evidence.

---

## 5. Data & citations

- `schemes.json` facts: `{id, scheme, field, value, applies_to{crops,season,states,events}, source_title, source_url, page, as_of, confidence}`. Built by a worker from the PMFBY Revamped OGs PDF and the TN Kharif 2026 notification. Unit test: every fact has url + as_of + page.
- `lookup_scheme` returns facts + `unknowns` (e.g., district sum insured, indemnity level, exact enrolment cut-off) with the sentence the agent should say for unknowns.
- Weather evidence stored per claim: request URL, raw JSON, derived metrics, thresholds used, verdict. Disaster evidence: GDACS event ids + report URLs.
- Crop plausibility: PMFBY crop calendar (district, crop, season windows) + data.gov.in APY stats (crop grown in district at all?).
- CRM claim view shows a **Citations** section: every scheme fact spoken, with clickable source and as-of; every data call with its URL and timestamp. Export as JSON/PDF.
- `docs/data-sources.md`: where each dataset comes from, how current, refresh procedure.

Weather truth-check algorithm (`check_weather`):
- Inputs: lat/lon, event_date (± window 2 days; cyclone/flood 3 days; drought 45 days back), damage_type.
- Source: Open-Meteo forecast API `past_days` if within 92 days, else archive API. Daily precipitation_sum, precipitation_hours, wind_gusts_10m_max, wind_speed_10m_max, temperature_2m_max; plus 30-day context for normals.
- Rules: cyclone → gust ≥ 60 km/h or GDACS TC event within 300 km; flood/inundation → 2-day rain ≥ 100 mm or GDACS FL; heavy rain/unseasonal rain → ≥ 50 mm/day; drought → 45-day rain < 30% of same-window prior-year archive; hail/pest/fire → "weather cannot confirm; field evidence needed" (never invented).
- Output: `verdict ∈ {supported, partially_supported, not_supported, unverifiable}`, numbers, sentence for the farmer, and `nearby_dates_that_match` (helps a farmer who misremembered the date).
- Down mode / timeout / error → `unverifiable` + escalate path; never "verified".

---

## 6. Dashboard / CRM (React)

- **Live Call**: transcript (from tool inputs during the call + full transcript after), slot state, grounding panel (weather request/response, disaster events, plausibility, scheme facts with citations), guardrail events (`say_safely` blocks, outcome-question redirects), risk score.
- **Claims (CRM)**: intake JSON, evidence, citations, status, audio/transcript link, export.
- **Tickets**: escalations with reasons, severity, "call farmer back" (outbound) and reviewer notes.
- **Red-team scoreboard**: latest run stats and drill-down transcripts.
- **Controls**: data-source down toggle, default language, outbound call by district/event (proactive mode), demo reset.

### 6.1 Evidence Upload Suite (farmer-facing, mobile)
- During the call, after `log_claim`/`escalate`, the agent calls `send_evidence_link` → backend creates a one-time signed URL for the claim and sends it via SnapServe `send_whatsapp` (fallback `send_sms`) to the caller's number. The agent tells the farmer, in their language, exactly which items to photograph.
- Page `/evidence/{token}` (mobile-first, works in WhatsApp's in-app browser, in the caller's language): a checklist generated from the claim (e.g., damaged-crop photos from 3 angles, land record / chitta-patta, sowing receipt, bank passbook, Aadhaar-masked ID), each with **camera capture** (`<input capture>` + preview), upload progress, retake, done state. Photos are stamped with client time and GPS if permitted, plus server receipt time.
- Uploads land on the claim in the CRM (Evidence tab): thumbnails, EXIF/GPS/timestamp, completeness meter, reviewer notes; dashboard updates live over WS. Optional Gemini vision check flags obviously wrong uploads (blank/blurred/not a crop) as "needs retake" — advisory only, never a decision.
- Late uploads (after the call) still attach; farmer can reopen the link until it expires; reviewer can re-send a link from the ticket.
- Storage: local disk in dev, S3-compatible bucket for judging day.

---

## 7. Phases (Opus workers; Fable reviews and integrates)

Phase 0 — Scaffold & platform probe (½ day)
- Backend skeleton, `.env`, SnapServe client, cloudflared tunnel script, a `/tools/echo` endpoint; create a throwaway SnapServe agent with one webhook tool and one webcall; capture the exact JSON SnapServe POSTs to a tool and the `call.completed` payload; confirm Gemini Live works with the Google key on the workspace (or enable Vertex API). Acceptance: documented payload shapes in `docs/snapserve-contract.md`; one successful Gemini Live webcall that hit our tool.

Phase 1 — Data services (parallel workers 1a/1b/1c)
- 1a weather + disasters + gazetteer + crops, with tests on known events (Gaja 2018, Chennai Dec 2015, a dry week) and the down-mode switch.
- 1b `schemes.json` from the PMFBY OGs and TN notification with page citations; retrieval + unknowns; tests.
- 1c claims/CRM store, tickets, escalation, WS bus, post-call ingestion + auditor.

Phase 2 — Tool layer + prompt (text-mode first)
- All `/tools/*` endpoints, slot memory, validators, safe scripts, language handling; a text-mode simulator that drives Gemini 3.6 Flash with the same prompt and tool schema so the whole flow can be tested without audio. Acceptance: scripted scenarios pass; validator tests with 150+ bait phrases across Tamil, Hindi, Telugu, Kannada, Malayalam, Marathi, Bengali, English and mixes.

Phase 3 — Red-team harness + scoreboard.

Phase 4 — SnapServe agent (real voice)
- Agent JSON (prompt, tools, transfer, silence/inactivity, voice), create/update script, webhook endpoint, webcall link, phone assignment, outbound trigger. Live tests in ≥ 3 languages with interruptions. Latency budget: tool responses < 800 ms p95.

Phase 5 — Dashboard/CRM + Evidence Upload Suite (mobile page, signed links, WhatsApp/SMS send tool, CRM Evidence tab).

Phase 6 — Docs & pitch: architecture one-pager + diagram, guardrails note, data-sources note, 5 transcripts + recordings (straightforward, fraud/ambiguous, distressed, code-switching, data-down), 3-minute pitch, Q&A sheet, runbook.

Phase 7 — Rehearsal: adversarial live calls, failure drills (weather down, tool timeout, call drop → SnapServe auto-redial), freeze.

---

## 8. Decisions needed from Kevin

1. **Phone number**: reassign +91 79658 54267 from "Priya" to the farmer agent for judging, or rent a second number (₹799/month)? Webcall link is available either way.
2. **Google key on SnapServe**: OK for us to add the Google key to the SnapServe workspace via the API? If SnapServe needs Vertex, you will have to enable the Vertex AI API on Google Cloud project 538591521478.
3. **Reviewer phone number** for the warm-transfer demo.
4. **Backend hosting** for judging day: your laptop + cloudflared, or a small cloud host (recommended)?
5. **Judging date** (to size phases).
6. **Optional**: an Anthropic key if you want Claude as the backend judge/simulator instead of Gemini Flash (not required).

## 9. Risks
- Native audio can speak before filtering → mitigated by tools-for-sensitive-turns, audit, eval evidence; stated openly.
- SnapServe tool payload shape unknown until probed → Phase 0.
- Gemini Live preview model changes → pin `gemini-3.1-flash-live-preview`, keep `gemini-2.5-flash-native-audio-latest` as fallback in the agent script.
- Public tunnel instability → cloud host for judging; cloudflared only for dev.
- Scheme specifics vary by state notification → agent says so and escalates; never guesses.
