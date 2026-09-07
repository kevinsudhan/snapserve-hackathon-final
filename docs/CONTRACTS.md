# Araxys Desk — Build Contracts (all workers read this first)

Product: **Araxys Desk** — a voice claims desk for farmers. SnapServe hosts the voice agent ("Sunil", agent id 1151, Gemini Live, Indian number +91 79658 54267). Our system is (1) the agent's knowledge + prompt, (2) a backend that ingests completed calls from SnapServe and builds a truth-checked claim record with citations, (3) a CRM dashboard for judges/reviewers, (4) a mobile evidence-upload page for farmers.

**Hard rules**
- The agent makes NO tool calls. All data it may quote is baked into its system prompt (weather snapshot, scheme facts, crop calendar, evidence checklists, safe scripts).
- Every fact the agent may speak carries a citation id like `[S12]` (scheme) or `[W-Cuddalore-2026-09-02]` (weather) that resolves in the CRM to a real URL.
- Backend never needs a public URL. It POLLS SnapServe (`GET /api/calls`) for completed calls.
- **NO live data fetching at runtime.** Weather + disaster data for the past 60 days (all 38 TN districts) is pulled ONCE by `services/knowledge_weather.py` (CLI) from Open-Meteo + GDACS into `backend/data/weather_snapshot.json`. The agent prompt, the CRM truth-check (`check_weather`/`check_disasters`) and the map all read that file. `POST /api/knowledge/refresh` re-runs the puller (manual, reviewer-triggered) and re-pushes the prompt; nothing else touches the network except SnapServe and Gemini.
- Any language. Nothing is Tamil-only. The caller's language is detected from the transcript and stored.
- Never fabricate data. If a source is unreachable, mark `unverifiable`, never `verified`.
- Do not edit files outside your ownership. Do not touch `.env`. Do not create a second venv; use `backend/.venv` (already has fastapi, uvicorn, sqlalchemy, httpx, pydantic v2, pydantic-settings, google-genai, pypdf, python-multipart, qrcode, pillow, pytest, rapidfuzz, python-dotenv, orjson). If you truly need another package, install it into that venv and append to `backend/requirements.txt`.

## Ownership
| Worker | Owns | Must not touch |
|---|---|---|
| data | `backend/services/weather.py`, `disasters.py`, `gazetteer.py`, `crops.py`, `knowledge_weather.py`, `backend/data/tn_districts.json`, `backend/data/crop_calendar_tn.json`, `backend/data/tn_districts.geojson`, `backend/tests/test_data_*.py` | app/, prompts/, schemes.* |
| schemes | `backend/services/schemes.py`, `backend/data/schemes.json`, `backend/data/evidence_checklists.json`, `backend/data/safe_scripts.json`, `backend/prompts/system_prompt.md`, `backend/prompts/knowledge_template.md`, `backend/tests/test_schemes.py`, `docs/data-sources.md` | app/, weather/disasters/gazetteer |
| core | `backend/app/**`, `backend/services/snapserve.py`, `gemini.py`, `poller.py`, `ingest.py`, `guardrail.py`, `knowledge.py`, `evidence.py`, `backend/prompts/extraction.md`, `audit.md`, `backend/scripts/*`, `backend/tests/test_core_*.py` | data/*.json owned by others, system_prompt.md |
| dashboard | `dashboard/**` | backend/** |

## Environment (`.env` at repo root, loaded by backend via pydantic-settings)
```
SNAPSERVE_API_KEY, SNAPSERVE_BASE_URL=https://app.snapserve.ai/api, SNAPSERVE_AGENT_ID=1151
GOOGLE_API_KEY, GEMINI_TEXT_MODEL=gemini-3.6-flash, GEMINI_LIVE_MODEL=gemini-3.1-flash-live-preview
REVIEWER_PHONE=+918939153390
BACKEND_PORT=8000, DASHBOARD_ORIGIN=http://localhost:5173, PUBLIC_BASE_URL=http://<lan-ip>:5173 (for evidence links/QR)
DATA_DIR=backend/data, DB_PATH=backend/data/araxysdesk.db, EVIDENCE_DIR=backend/data/evidence
POLL_INTERVAL_SECONDS=3, DATA_DOWN_MODE=false
```

## Backend HTTP API (FastAPI, `http://localhost:8000`, JSON, CORS open to DASHBOARD_ORIGIN and LAN)
```
GET  /api/health                         → {ok, version, snapserve_ok, gemini_ok, poller:{running,last_poll_at}, data_down_mode}
GET  /api/stats                          → {calls_total, claims_total, tickets_open, guardrail_incidents, languages:{code:count}, verdicts:{supported,partially_supported,not_supported,unverifiable}, last_24h:[{hour,calls}]}
GET  /api/calls?limit=50                 → CallRecord[] (newest first)
GET  /api/calls/{id}                     → CallRecord
GET  /api/claims?status=&q=              → Claim[] (summary fields)
GET  /api/claims/{id}                    → Claim (full, with evidence + citations)
PATCH /api/claims/{id}                   body {status?, reviewer_notes?} → Claim
GET  /api/tickets?status=                → Ticket[]
PATCH /api/tickets/{id}                  body {status?, reviewer_notes?} → Ticket
POST /api/claims/{id}/evidence-link      → {token, url, qr_svg (string), whatsapp_url, expires_at}
GET  /api/evidence/{token}               → {claim_reference, farmer_language, items:[{key,label,label_local,instructions_local,required,uploaded:[EvidenceFile]}], expires_at}
POST /api/evidence/{token}/upload        multipart: item_key, file, client_time?, lat?, lon? → EvidenceFile
GET  /api/evidence/files/{file_id}       → binary (image)
GET  /api/knowledge/status               → {last_refresh_at, agent_synced_at, districts, days, notable_events, approx_tokens, sources:[Citation]}
POST /api/knowledge/refresh              → re-run the one-off snapshot puller (60 days, real sources), re-render prompt, push to SnapServe agent → KnowledgeStatus
GET  /api/knowledge/geo                  → Tamil Nadu districts GeoJSON (backend/data/tn_districts.geojson)
GET  /api/knowledge/snapshot             → WeatherSnapshot (JSON)
GET  /api/knowledge/prompt               → {system_prompt: string, approx_tokens}
GET  /api/citations/{id}                 → Citation
POST /api/admin/simulate                 body {transcript: string, from_number?: string, language?: string} → CallRecord (runs the full ingest pipeline; used for demos/tests)
POST /api/admin/data-down                body {enabled: bool} → {enabled}
POST /api/admin/reset-demo               → clears calls/claims/tickets (keeps knowledge)
GET  /api/eval/latest                    → EvalReport | null
POST /api/eval/run                       body {scenarios?: string[], n?: int} → starts background run; progress via WS
WS   /ws/events                          → server pushes Event JSON (see below); client may send {"type":"ping"}
```

## Event (WebSocket)
```
{ "type": "call.started" | "call.completed" | "claim.created" | "claim.updated" | "ticket.created" | "ticket.updated" | "evidence.uploaded" | "knowledge.refreshed" | "guardrail.incident" | "eval.progress" | "eval.completed" | "poller.status",
  "at": ISO8601, "payload": object }
```

## Data shapes (pydantic in `backend/app/schemas.py`; TypeScript mirror in `dashboard/src/types.ts`)
```ts
type Citation = { id: string; title: string; url: string; publisher: string; page?: number|string; as_of: string; quote?: string; kind: "scheme"|"weather"|"disaster"|"crop"|"gazetteer"|"other" }

type TranscriptTurn = { i: number; role: "agent"|"caller"; text: string; language?: string; flags?: string[] }

type CallRecord = { id: number; snapserve_call_id: string; direction: "inbound"|"outbound"|"webcall"|"simulated"; from_number?: string; to_number?: string; status: "in_progress"|"completed"|"failed"|"no_pickup";
  started_at: string; ended_at?: string; duration_seconds?: number; language_detected?: string; languages?: string[]; code_switching: boolean;
  transcript: TranscriptTurn[]; summary?: string; recording_url?: string; claim_id?: number; ticket_id?: number;
  guardrail_incidents: GuardrailIncident[]; processing: "pending"|"processing"|"done"|"error"; processing_error?: string }

type GuardrailIncident = { turn_index: number; category: "payout_promise"|"approval_promise"|"timeline_promise"|"fabricated_scheme"|"out_of_scope_advice"|"missed_escalation"|"other"; text: string; severity: "low"|"medium"|"high"; detector: "rules"|"llm" }

type LandExtent = { value: number; unit: string; hectares: number }
type Location = { village?: string; taluk?: string; district?: string; state: string; lat?: number; lon?: number; resolution_confidence: number; resolved_by?: string; citation_id?: string }

type WeatherDay = { date: string; precipitation_mm: number; wind_gust_kmh: number; temp_max_c: number }
type WeatherEvidence = { source: "snapshot"|"none"; request_url?: string; fetched_at?: string; window: {start: string; end: string}; daily: WeatherDay[]; context_30d_rain_mm?: number;
  metrics: Record<string, number>; verdict: "supported"|"partially_supported"|"not_supported"|"unverifiable"; reasons: string[]; farmer_sentence: string; nearby_matching_dates: string[]; citations: Citation[] }
type DisasterEvent = { id: string; type: string; name: string; alert_level: string; from: string; to: string; distance_km?: number; report_url: string }
type DisasterEvidence = { source: "gdacs"|"none"; fetched_at?: string; events: DisasterEvent[]; citations: Citation[] }
type CropEvidence = { crop: string; district?: string; season?: string; in_window: boolean|null; window?: {sowing: string; harvest: string}; note: string; citations: Citation[] }
type SchemeMatch = { fact_id: string; scheme: string; field: string; text: string; citation: Citation }
type EvidenceItem = { key: string; label: string; label_local?: string; why: string; citation_id?: string; required: boolean }
type EvidenceFile = { id: string; item_key: string; filename: string; content_type: string; size: number; uploaded_at: string; client_time?: string; lat?: number; lon?: number; url: string; quality_flag?: "ok"|"blurry"|"not_relevant"|"unchecked" }
type RiskSignal = { code: string; description: string; weight: number }
type Risk = { score: number; level: "low"|"medium"|"high"; signals: RiskSignal[] }

type Claim = { id: number; reference: string; call_id: number; status: "logged"|"escalated"|"under_review"|"approved_for_survey"|"closed";
  farmer: { name?: string; phone?: string; language: string };
  crop?: string; land_extent?: LandExtent; damage_type?: string; event_date?: string; event_date_confidence: number; location: Location; narrative: string;
  weather_evidence: WeatherEvidence; disaster_evidence: DisasterEvidence; crop_evidence?: CropEvidence;
  scheme_matches: SchemeMatch[]; unknowns: string[]; evidence_required: EvidenceItem[]; evidence_uploads: EvidenceFile[];
  risk: Risk; escalation_reason?: string; farmer_explanation?: string; reviewer_notes?: string; created_at: string; updated_at: string;
  agent_said_facts: { fact_id: string; verified: boolean }[]  // which citation ids the agent actually quoted, cross-checked against transcript
}

type Ticket = { id: number; claim_id: number; call_id: number; reference: string; severity: "low"|"medium"|"high"; reasons: string[]; farmer_explanation: string; status: "open"|"in_review"|"resolved"|"rejected"; reviewer_notes?: string; created_at: string; updated_at: string }

type WeatherSnapshot = { generated_at: string; days: number; districts: { name: string; lat: number; lon: number; source_url: string; daily: WeatherDay[]; notable: string[] }[]; disasters: DisasterEvent[]; citations: Citation[] }

type EvalReport = { run_id: string; started_at: string; finished_at?: string; n_calls: number; languages: string[]; results: { scenario: string; language: string; passed: boolean; promise_leaks: number; fabrications: number; escalation_ok: boolean; one_question_rate: number; transcript: TranscriptTurn[] }[]; totals: { promise_leaks: number; fabrications: number; escalation_failures: number; pass_rate: number } }
```

## Service function signatures (data + schemes workers implement; core imports)
```python
# backend/services/gazetteer.py
def resolve_location(village: str|None, taluk: str|None, district: str|None, state: str = "Tamil Nadu") -> Location   # OFFLINE: fuzzy district/taluk/alias tables; unknown village → district centroid with low confidence; sets resolved_by + citation_id
def list_districts() -> list[dict]   # [{name, lat, lon}] for Tamil Nadu (38)

# backend/services/weather.py
def check_weather(lat: float, lon: float, event_date: str, damage_type: str, *, data_down: bool = False) -> WeatherEvidence
def fetch_daily(lat: float, lon: float, start: str, end: str) -> tuple[list[WeatherDay], str]  # reads ONLY weather_snapshot.json (nearest district centroid); (days, source_request_url)
DAMAGE_TYPES = ["cyclone","flood","inundation","heavy_rain","unseasonal_rain","drought","hailstorm","pest","disease","fire","landslide","other"]

# backend/services/disasters.py
def check_disasters(lat: float, lon: float, event_date: str, *, radius_km: float = 300, days: int = 5, data_down: bool = False) -> DisasterEvidence  # GDACS TC/FL/DR read from the snapshot only

# backend/services/crops.py
def check_crop_window(crop: str, district: str|None, event_date: str) -> CropEvidence
def normalize_crop(text: str) -> str|None          # "nel", "paddy", "rice", "vari", "dhan" → "paddy"
def normalize_land_extent(value: float, unit_text: str) -> LandExtent   # acre, cent, hectare, bigha, guntha, kani, ma, ground

# backend/services/knowledge_weather.py
def build_weather_snapshot(days: int = 60, *, data_down: bool = False) -> WeatherSnapshot   # THE ONLY network call to Open-Meteo + GDACS; CLI `python -m services.knowledge_weather --days 60` from backend/; writes backend/data/weather_snapshot.json
def render_weather_knowledge(snapshot: WeatherSnapshot) -> str   # compact prompt text: coverage rule line, per-district totals + weekly lines + notable days [W-<District>-<date>], GDACS [D-<id>]; ≤ ~15k tokens
def load_snapshot() -> WeatherSnapshot   # cached read of weather_snapshot.json

# backend/services/schemes.py
def load_facts() -> list[dict]                     # schemes.json entries: {id:"S1", scheme, field, text, applies_to:{crops,seasons,states,events}, citation: Citation}
def lookup_scheme(crop: str|None, district: str|None, event_date: str|None, damage_type: str|None) -> tuple[list[SchemeMatch], list[str]]   # (matches, unknowns)
def evidence_checklist(damage_type: str|None, crop: str|None) -> list[EvidenceItem]
def render_scheme_knowledge() -> str               # text for the prompt with [S#] ids
def safe_scripts() -> dict                          # {"payout_question": {...}, "approval_question": ..., "timeline_question": ..., "escalation": ..., "data_unavailable": ...} English canonical + guidance to render in caller language
def citation_by_id(cid: str) -> Citation|None      # S#, W-*, C-*, G-* ids
```

## Prompt assembly (core: `services/knowledge.py`)
`system_prompt.md` contains placeholders `{{SCHEME_KNOWLEDGE}}`, `{{WEATHER_KNOWLEDGE}}`, `{{CROP_CALENDAR}}`, `{{EVIDENCE_CHECKLISTS}}`, `{{SAFE_SCRIPTS}}`, `{{REVIEWER_PHONE}}`, `{{GENERATED_AT}}`. Core renders and pushes via `PATCH/PUT /api/agents/{id}` (check which verb SnapServe accepts; GET first, then update `systemPrompt`, `llmProvider:"google"`, `llmModel:"gemini-3.1-flash-live-preview"`, `voiceStack:"gemini_live"`, `language`, transfer tool to REVIEWER_PHONE, `silenceTimeoutSeconds`, `inactivityMessage`, `greetingMessage`, `dispositionSchema`).

## Ingest pipeline (core: `services/ingest.py`) — runs for every completed call
1. Parse SnapServe transcript ("Agent: …\nCaller: …") → TranscriptTurn[]; detect languages + code-switching (Gemini).
2. Gemini extraction (JSON schema): farmer name/phone, crop, land extent, damage_type, event_date (absolute, from call date), location parts, narrative, distress flag, asked_for_human, outcome questions asked, facts the agent quoted (citation ids), evidence agent listed.
3. resolve_location → check_weather + check_disasters + check_crop_window (all from the real-data SNAPSHOT file; honours DATA_DOWN_MODE) → lookup_scheme → evidence_checklist.
4. Risk scoring (rules): weather not_supported (+40), unverifiable (+25), partially (+10); contradictions in transcript (+15 each); land extent > 20 ha (+15); crop out of window (+15); event date > 72h before call for localized calamity (+5, informational); distress (+0 but escalate); asked_for_human (escalate); agent quoted a citation id that doesn't exist (+20 and guardrail incident).
5. Guardrail audit: rules (multilingual regex list in `guardrail.py`) + Gemini judge over agent turns → GuardrailIncident[].
6. Decide: risk ≥ 40 or unverifiable or distress or asked_for_human → Ticket (with `farmer_explanation` — non-accusatory) and Claim.status="escalated"; else Claim.status="logged".
7. Emit WS events at each step (claim.created first with partial data, then claim.updated as evidence arrives — the dashboard animates facts appearing).

## Dashboard (owner: dashboard) — pages
`/` Overview · `/live` Live Desk (calls in progress + latest completed, truth panel animating) · `/claims` + `/claims/:id` (Truth panel: rain/wind chart with event window highlighted, verdict, disaster events, crop window, scheme facts with citation chips → source URL, risk gauge & signals, transcript with flags, evidence gallery, evidence-link QR) · `/tickets` (kanban: open / in review / resolved) · `/knowledge` (snapshot status, TN district map coloured by 7-day rain, sources list, prompt preview, Refresh button) · `/guardrails` (incidents + eval scoreboard) · `/e/:token` (public mobile evidence upload page, no nav chrome).
Dev: Vite proxy `/api` and `/ws` → `http://localhost:8000`. `VITE_MOCK=1` serves realistic mock data + fake WS stream so UI can be built before backend exists.
