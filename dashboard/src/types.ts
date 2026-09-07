/**
 * TypeScript mirror of `backend/app/schemas.py` — see docs/CONTRACTS.md.
 * Keep field names identical to the pydantic models; the dashboard never
 * renames server fields.
 */

export type CitationKind =
  | 'scheme'
  | 'weather'
  | 'disaster'
  | 'crop'
  | 'gazetteer'
  | 'other'

export type Citation = {
  id: string
  title: string
  url: string
  publisher: string
  page?: number | string
  as_of: string
  quote?: string
  kind: CitationKind
}

export type TranscriptTurn = {
  i: number
  role: 'agent' | 'caller'
  text: string
  language?: string
  flags?: string[]
}

export type GuardrailCategory =
  | 'payout_promise'
  | 'approval_promise'
  | 'timeline_promise'
  | 'fabricated_scheme'
  | 'out_of_scope_advice'
  | 'missed_escalation'
  | 'other'

export type GuardrailIncident = {
  turn_index: number
  category: GuardrailCategory
  text: string
  severity: 'low' | 'medium' | 'high'
  detector: 'rules' | 'llm'
}

export type CallStatus = 'in_progress' | 'completed' | 'failed' | 'no_pickup'
export type CallDirection = 'inbound' | 'outbound' | 'webcall' | 'simulated'

export type CallRecord = {
  id: number
  snapserve_call_id: string
  direction: CallDirection
  from_number?: string
  to_number?: string
  status: CallStatus
  started_at: string
  ended_at?: string
  duration_seconds?: number
  language_detected?: string
  languages?: string[]
  code_switching: boolean
  transcript: TranscriptTurn[]
  summary?: string
  recording_url?: string
  claim_id?: number
  ticket_id?: number
  guardrail_incidents: GuardrailIncident[]
  processing: 'pending' | 'processing' | 'done' | 'error'
  processing_error?: string
}

export type LandExtent = { value: number; unit: string; hectares: number }

export type Location = {
  village?: string
  taluk?: string
  district?: string
  state: string
  lat?: number
  lon?: number
  resolution_confidence: number
  resolved_by?: string
  citation_id?: string
}

export type WeatherDay = {
  date: string
  precipitation_mm: number
  wind_gust_kmh: number
  temp_max_c: number
}

export type Verdict =
  | 'supported'
  | 'partially_supported'
  | 'not_supported'
  | 'unverifiable'

export type WeatherEvidence = {
  source: 'snapshot' | 'none'
  request_url?: string
  fetched_at?: string
  window: { start: string; end: string }
  daily: WeatherDay[]
  context_30d_rain_mm?: number
  metrics: Record<string, number>
  verdict: Verdict
  reasons: string[]
  farmer_sentence: string
  nearby_matching_dates: string[]
  citations: Citation[]
}

export type DisasterEvent = {
  id: string
  type: string
  name: string
  alert_level: string
  from: string
  to: string
  distance_km?: number
  report_url: string
}

export type DisasterEvidence = {
  source: 'gdacs' | 'none'
  fetched_at?: string
  events: DisasterEvent[]
  citations: Citation[]
}

export type CropEvidence = {
  crop: string
  district?: string
  season?: string
  in_window: boolean | null
  window?: { sowing: string; harvest: string }
  note: string
  citations: Citation[]
}

export type SchemeMatch = {
  fact_id: string
  scheme: string
  field: string
  text: string
  citation: Citation
}

export type EvidenceItem = {
  key: string
  label: string
  label_local?: string
  why: string
  citation_id?: string
  required: boolean
}

export type EvidenceFile = {
  id: string
  item_key: string
  filename: string
  content_type: string
  size: number
  uploaded_at: string
  client_time?: string
  lat?: number
  lon?: number
  url: string
  quality_flag?: 'ok' | 'blurry' | 'not_relevant' | 'unchecked'
}

export type RiskSignal = { code: string; description: string; weight: number }

export type Risk = {
  score: number
  level: 'low' | 'medium' | 'high'
  signals: RiskSignal[]
}

export type ClaimStatus =
  | 'logged'
  | 'escalated'
  | 'under_review'
  | 'approved_for_survey'
  | 'closed'

export type Claim = {
  id: number
  reference: string
  call_id: number
  status: ClaimStatus
  farmer: { name?: string; phone?: string; language: string }
  crop?: string
  land_extent?: LandExtent
  damage_type?: string
  event_date?: string
  event_date_confidence: number
  location: Location
  narrative: string
  weather_evidence: WeatherEvidence
  disaster_evidence: DisasterEvidence
  crop_evidence?: CropEvidence
  scheme_matches: SchemeMatch[]
  unknowns: string[]
  evidence_required: EvidenceItem[]
  evidence_uploads: EvidenceFile[]
  risk: Risk
  escalation_reason?: string
  farmer_explanation?: string
  reviewer_notes?: string
  created_at: string
  updated_at: string
  /** citation ids the agent actually quoted, cross-checked against the transcript */
  agent_said_facts: { fact_id: string; verified: boolean }[]
}

export type TicketStatus = 'open' | 'in_review' | 'resolved' | 'rejected'

export type Ticket = {
  id: number
  claim_id: number
  call_id: number
  reference: string
  severity: 'low' | 'medium' | 'high'
  reasons: string[]
  farmer_explanation: string
  status: TicketStatus
  reviewer_notes?: string
  created_at: string
  updated_at: string
}

export type SnapshotDistrict = {
  name: string
  lat: number
  lon: number
  source_url: string
  daily: WeatherDay[]
  notable: string[]
}

export type WeatherSnapshot = {
  generated_at: string
  days: number
  districts: SnapshotDistrict[]
  disasters: DisasterEvent[]
  citations: Citation[]
}

export type EvalResult = {
  scenario: string
  language: string
  passed: boolean
  promise_leaks: number
  fabrications: number
  escalation_ok: boolean
  one_question_rate: number
  transcript: TranscriptTurn[]
}

export type EvalReport = {
  run_id: string
  started_at: string
  finished_at?: string
  n_calls: number
  languages: string[]
  results: EvalResult[]
  totals: {
    promise_leaks: number
    fabrications: number
    escalation_failures: number
    pass_rate: number
  }
}

/* ---------- endpoint envelopes ---------- */

export type Health = {
  ok: boolean
  version: string
  snapserve_ok: boolean
  gemini_ok: boolean
  poller: { running: boolean; last_poll_at?: string }
  data_down_mode: boolean
}

export type Stats = {
  calls_total: number
  claims_total: number
  tickets_open: number
  guardrail_incidents: number
  languages: Record<string, number>
  verdicts: Record<Verdict, number>
  last_24h: { hour: string; calls: number }[]
}

export type KnowledgeStatus = {
  last_refresh_at?: string
  agent_synced_at?: string
  districts: number
  days: number
  notable_events: number
  approx_tokens: number
  sources: Citation[]
}

export type EvidenceLink = {
  token: string
  url: string
  qr_svg: string
  whatsapp_url: string
  expires_at: string
}

export type EvidencePortalItem = {
  key: string
  label: string
  label_local?: string
  instructions_local?: string
  required: boolean
  uploaded: EvidenceFile[]
}

export type EvidencePortal = {
  claim_reference: string
  farmer_language: string
  items: EvidencePortalItem[]
  expires_at: string
}

/* ---------- WebSocket ---------- */

export type EventType =
  | 'call.started'
  | 'call.completed'
  | 'claim.created'
  | 'claim.updated'
  | 'ticket.created'
  | 'ticket.updated'
  | 'evidence.uploaded'
  | 'knowledge.refreshed'
  | 'guardrail.incident'
  | 'eval.progress'
  | 'eval.completed'
  | 'poller.status'

export type LiveEvent<P = Record<string, unknown>> = {
  type: EventType
  at: string
  payload: P
}

/** GeoJSON subset used by the Tamil Nadu choropleth. */
export type GeoFeature = {
  type: 'Feature'
  properties: Record<string, unknown>
  geometry: {
    type: 'Polygon' | 'MultiPolygon'
    coordinates: number[][][] | number[][][][]
  }
}

export type GeoCollection = { type: 'FeatureCollection'; features: GeoFeature[] }
