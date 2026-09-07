/**
 * In-browser mock backend for `VITE_MOCK=1`.
 *
 * `mockFetch` answers every REST route in docs/CONTRACTS.md, and
 * `MockSocket` is a drop-in WebSocket that replays a full call lifecycle
 * (call.started → claim.created → several claim.updated → ticket.created /
 * evidence.uploaded → call.completed) roughly every 20 seconds.
 */
import type {
  CallRecord,
  Claim,
  EvidenceFile,
  EvidencePortal,
  LiveEvent,
  Ticket,
} from '@/types'
import {
  CALLS,
  CLAIMS,
  ENQUIRY_CALLS,
  EVAL_REPORT,
  HEALTH,
  KNOWLEDGE_STATUS,
  SNAPSHOT,
  SCHEME_FACTS,
  TICKETS,
  buildLiveClaim,
  buildStats,
  iso,
  liveTranscript,
  makeQrSvg,
  mockPhoto,
} from './data'

/* ------------------------------------------------------------------ *
 * mutable state
 * ------------------------------------------------------------------ */

const state = {
  calls: [...CALLS, ...ENQUIRY_CALLS],
  claims: [...CLAIMS],
  tickets: [...TICKETS],
  dataDown: false,
  knowledge: { ...KNOWLEDGE_STATUS },
  evalReport: EVAL_REPORT,
  seq: 0,
  nextCallId: 3000,
  uploads: new Map<string, EvidenceFile[]>(),
}

export const mockState = state

type Listener = (e: LiveEvent) => void
const listeners = new Set<Listener>()

function emit(type: LiveEvent['type'], payload: Record<string, unknown>) {
  const event: LiveEvent = { type, at: iso(Date.now()), payload }
  listeners.forEach((l) => {
    try {
      l(event)
    } catch {
      /* a bad subscriber must not break the stream */
    }
  })
}

/* ------------------------------------------------------------------ *
 * REST
 * ------------------------------------------------------------------ */

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

const LATENCY = 90

function summaryClaim(c: Claim) {
  return c
}

function portalFor(claim: Claim): EvidencePortal {
  const extra = state.uploads.get(claim.reference) ?? []
  return {
    claim_reference: claim.reference,
    farmer_language: claim.farmer.language,
    items: claim.evidence_required.map((item) => ({
      key: item.key,
      label: item.label,
      label_local: item.label_local,
      instructions_local: item.why,
      required: item.required,
      uploaded: [...claim.evidence_uploads, ...extra].filter((f) => f.item_key === item.key),
    })),
    expires_at: iso(Date.now() + 3 * 86_400_000),
  }
}

/** mock tokens look like `ev_1041_h3k9qz`; anything else falls back to the newest claim */
function claimForToken(token: string): Claim {
  const id = Number(token.split('_')[1])
  return state.claims.find((c) => c.id === id) ?? state.claims[0]
}

export async function mockFetch(input: string, init?: RequestInit): Promise<Response> {
  await new Promise((r) => setTimeout(r, LATENCY))
  const url = new URL(input, window.location.origin)
  const path = url.pathname
  const method = (init?.method ?? 'GET').toUpperCase()
  const body = init?.body && typeof init.body === 'string' ? JSON.parse(init.body) : undefined

  /* ---- health / stats ---- */
  if (path === '/api/health') {
    return json({
      ...HEALTH,
      data_down_mode: state.dataDown,
      poller: { running: true, last_poll_at: iso(Date.now() - 1500) },
    })
  }
  if (path === '/api/stats') {
    return json(buildStats(state.claims, state.calls, state.tickets))
  }

  /* ---- calls ---- */
  if (path === '/api/calls') {
    const limit = Number(url.searchParams.get('limit') ?? 50)
    return json([...state.calls].sort(byStartedDesc).slice(0, limit))
  }
  const callMatch = path.match(/^\/api\/calls\/(\d+)$/)
  if (callMatch) {
    const c = state.calls.find((x) => x.id === Number(callMatch[1]))
    return c ? json(c) : json({ detail: 'not found' }, 404)
  }

  /* ---- claims ---- */
  if (path === '/api/claims' && method === 'GET') {
    const status = url.searchParams.get('status')
    const q = (url.searchParams.get('q') ?? '').toLowerCase()
    let out = [...state.claims].sort(byCreatedDesc)
    if (status) out = out.filter((c) => c.status === status)
    if (q) {
      out = out.filter((c) =>
        [
          c.reference,
          c.crop,
          c.damage_type,
          c.farmer.name,
          c.farmer.phone,
          c.location.village,
          c.location.taluk,
          c.location.district,
        ]
          .filter(Boolean)
          .some((v) => String(v).toLowerCase().includes(q)),
      )
    }
    return json(out.map(summaryClaim))
  }
  const claimMatch = path.match(/^\/api\/claims\/(\d+)$/)
  if (claimMatch) {
    const id = Number(claimMatch[1])
    const idx = state.claims.findIndex((c) => c.id === id)
    if (idx < 0) return json({ detail: 'not found' }, 404)
    if (method === 'PATCH') {
      state.claims[idx] = {
        ...state.claims[idx],
        ...(body?.status ? { status: body.status } : {}),
        ...(body?.reviewer_notes !== undefined ? { reviewer_notes: body.reviewer_notes } : {}),
        updated_at: iso(Date.now()),
      }
      emit('claim.updated', { claim: state.claims[idx] })
    }
    return json(state.claims[idx])
  }
  const linkMatch = path.match(/^\/api\/claims\/(\d+)\/evidence-link$/)
  if (linkMatch && method === 'POST') {
    const claim = state.claims.find((c) => c.id === Number(linkMatch[1])) ?? state.claims[0]
    const token = `ev_${claim.id}_${Math.random().toString(36).slice(2, 8)}`
    const link = `${window.location.origin}/e/${token}`
    const message = `Araxys Desk: photos for claim ${claim.reference}. Open this link to upload: ${link}`
    return json({
      token,
      url: link,
      qr_svg: makeQrSvg(link),
      whatsapp_url: `https://wa.me/${(claim.farmer.phone ?? '').replace(/\D/g, '')}?text=${encodeURIComponent(message)}`,
      expires_at: iso(Date.now() + 3 * 86_400_000),
    })
  }

  /* ---- tickets ---- */
  if (path === '/api/tickets' && method === 'GET') {
    const status = url.searchParams.get('status')
    let out = [...state.tickets].sort(byCreatedDesc)
    if (status) out = out.filter((t) => t.status === status)
    return json(out)
  }
  const ticketMatch = path.match(/^\/api\/tickets\/(\d+)$/)
  if (ticketMatch && method === 'PATCH') {
    const id = Number(ticketMatch[1])
    const idx = state.tickets.findIndex((t) => t.id === id)
    if (idx < 0) return json({ detail: 'not found' }, 404)
    state.tickets[idx] = {
      ...state.tickets[idx],
      ...(body?.status ? { status: body.status } : {}),
      ...(body?.reviewer_notes !== undefined ? { reviewer_notes: body.reviewer_notes } : {}),
      updated_at: iso(Date.now()),
    }
    emit('ticket.updated', { ticket: state.tickets[idx] })
    return json(state.tickets[idx])
  }

  /* ---- evidence portal ---- */
  const portalMatch = path.match(/^\/api\/evidence\/([^/]+)$/)
  if (portalMatch && method === 'GET') {
    return json(portalFor(claimForToken(portalMatch[1])))
  }
  const uploadMatch = path.match(/^\/api\/evidence\/([^/]+)\/upload$/)
  if (uploadMatch && method === 'POST') {
    const claim = claimForToken(uploadMatch[1])
    const form = init?.body as FormData
    const file = form.get('file') as File
    const itemKey = String(form.get('item_key'))
    const record: EvidenceFile = {
      id: `up_${Math.random().toString(36).slice(2, 10)}`,
      item_key: itemKey,
      filename: file?.name ?? 'photo.jpg',
      content_type: file?.type ?? 'image/jpeg',
      size: file?.size ?? 0,
      uploaded_at: iso(Date.now()),
      client_time: String(form.get('client_time') ?? ''),
      lat: form.get('lat') ? Number(form.get('lat')) : undefined,
      lon: form.get('lon') ? Number(form.get('lon')) : undefined,
      url: file ? URL.createObjectURL(file) : '',
      quality_flag: 'unchecked',
    }
    const prev = state.uploads.get(claim.reference) ?? []
    state.uploads.set(claim.reference, [...prev, record])
    const idx = state.claims.findIndex((c) => c.id === claim.id)
    if (idx >= 0) {
      state.claims[idx] = {
        ...state.claims[idx],
        evidence_uploads: [...state.claims[idx].evidence_uploads, record],
        updated_at: iso(Date.now()),
      }
    }
    emit('evidence.uploaded', { claim_id: claim.id, claim_reference: claim.reference, file: record })
    return json(record)
  }

  /* ---- knowledge ---- */
  if (path === '/api/knowledge/status') return json(state.knowledge)
  if (path === '/api/knowledge/snapshot') return json(SNAPSHOT)
  if (path === '/api/knowledge/prompt') {
    return json({ system_prompt: MOCK_PROMPT, approx_tokens: state.knowledge.approx_tokens })
  }
  if (path === '/api/knowledge/geo') {
    const res = await fetch('/tn_districts.geojson')
    return json(await res.json())
  }
  if (path === '/api/knowledge/refresh' && method === 'POST') {
    await new Promise((r) => setTimeout(r, 1600))
    state.knowledge = {
      ...state.knowledge,
      last_refresh_at: iso(Date.now()),
      agent_synced_at: iso(Date.now() + 1000),
      approx_tokens: 14_820 + Math.floor(Math.random() * 400),
    }
    emit('knowledge.refreshed', { status: state.knowledge })
    return json(state.knowledge)
  }

  /* ---- citations ---- */
  const citationMatch = path.match(/^\/api\/citations\/(.+)$/)
  if (citationMatch) {
    const id = decodeURIComponent(citationMatch[1])
    const fact = SCHEME_FACTS.find((f) => f.fact_id === id)
    if (fact) return json(fact.citation)
    const src = SNAPSHOT.citations.find((c) => c.id === id)
    return src ? json(src) : json({ detail: 'not found' }, 404)
  }

  /* ---- eval ---- */
  if (path === '/api/eval/latest') return json(state.evalReport)
  if (path === '/api/eval/run' && method === 'POST') {
    runMockEval()
    return json({ started: true })
  }

  /* ---- admin ---- */
  if (path === '/api/admin/data-down' && method === 'POST') {
    state.dataDown = Boolean(body?.enabled)
    emit('poller.status', { data_down_mode: state.dataDown, running: true })
    return json({ enabled: state.dataDown })
  }
  if (path === '/api/admin/reset-demo' && method === 'POST') {
    state.calls = [...CALLS, ...ENQUIRY_CALLS]
    state.claims = [...CLAIMS]
    state.tickets = [...TICKETS]
    state.uploads.clear()
    return json({ ok: true })
  }
  if (path === '/api/admin/simulate' && method === 'POST') {
    runScenario()
    return json({ started: true })
  }

  return json({ detail: `mock: no route for ${method} ${path}` }, 404)
}

function byStartedDesc(a: CallRecord, b: CallRecord) {
  return +new Date(b.started_at) - +new Date(a.started_at)
}
function byCreatedDesc(a: { created_at: string }, b: { created_at: string }) {
  return +new Date(b.created_at) - +new Date(a.created_at)
}

/* ------------------------------------------------------------------ *
 * scripted live scenario
 * ------------------------------------------------------------------ */

const timers: number[] = []
function at(ms: number, fn: () => void) {
  timers.push(window.setTimeout(fn, ms))
}

/** Progressive disclosure: each stage reveals another block of the claim. */
function stageClaim(full: Claim, stage: number): Claim {
  const blank = {
    source: 'none' as const,
    window: { start: '', end: '' },
    daily: [],
    metrics: {},
    verdict: 'unverifiable' as const,
    reasons: [],
    farmer_sentence: '',
    nearby_matching_dates: [],
    citations: [],
  }
  if (stage === 0) {
    return {
      ...full,
      status: 'logged',
      location: { ...full.location, resolution_confidence: 0.0, resolved_by: undefined },
      weather_evidence: blank,
      disaster_evidence: { source: 'none', events: [], citations: [] },
      crop_evidence: undefined,
      scheme_matches: [],
      unknowns: [],
      evidence_required: [],
      risk: { score: 0, level: 'low', signals: [] },
      escalation_reason: undefined,
      farmer_explanation: undefined,
    }
  }
  if (stage === 1) {
    return {
      ...full,
      status: 'logged',
      weather_evidence: blank,
      disaster_evidence: { source: 'none', events: [], citations: [] },
      scheme_matches: [],
      unknowns: [],
      evidence_required: [],
      risk: { score: 0, level: 'low', signals: [] },
      escalation_reason: undefined,
      farmer_explanation: undefined,
    }
  }
  if (stage === 2) {
    return {
      ...full,
      status: 'logged',
      disaster_evidence: { source: 'none', events: [], citations: [] },
      scheme_matches: [],
      unknowns: [],
      evidence_required: [],
      risk: { score: 0, level: 'low', signals: [] },
      escalation_reason: undefined,
      farmer_explanation: undefined,
    }
  }
  if (stage === 3) {
    return {
      ...full,
      status: 'logged',
      risk: { score: 0, level: 'low', signals: [] },
      escalation_reason: undefined,
      farmer_explanation: undefined,
    }
  }
  return full
}

function upsertClaim(c: Claim) {
  const idx = state.claims.findIndex((x) => x.id === c.id)
  if (idx >= 0) state.claims[idx] = c
  else state.claims.unshift(c)
}

function upsertCall(c: CallRecord) {
  const idx = state.calls.findIndex((x) => x.id === c.id)
  if (idx >= 0) state.calls[idx] = c
  else state.calls.unshift(c)
}

export function runScenario() {
  const seq = state.seq++
  const callId = state.nextCallId++
  const { claim, call } = buildLiveClaim(seq, callId)
  const transcript = liveTranscript(claim)

  upsertCall(call)
  emit('call.started', { call })

  at(2600, () => {
    const partial = stageClaim(claim, 0)
    upsertClaim(partial)
    upsertCall({ ...call, transcript: transcript.slice(0, 6) })
    emit('claim.created', { claim: partial })
  })

  at(5200, () => {
    const partial = stageClaim(claim, 1)
    upsertClaim(partial)
    upsertCall({ ...call, transcript: transcript.slice(0, 10) })
    emit('claim.updated', { claim: partial, step: 'location_resolved' })
  })

  at(8000, () => {
    const partial = stageClaim(claim, 2)
    upsertClaim(partial)
    emit('claim.updated', { claim: partial, step: 'weather_checked' })
  })

  at(10_600, () => {
    const partial = stageClaim(claim, 3)
    upsertClaim(partial)
    upsertCall({ ...call, transcript: transcript.slice(0, 14) })
    emit('claim.updated', { claim: partial, step: 'schemes_matched' })
  })

  at(13_200, () => {
    upsertClaim(claim)
    emit('claim.updated', { claim, step: 'risk_scored' })
  })

  at(15_400, () => {
    const done: CallRecord = {
      ...call,
      status: 'completed',
      ended_at: iso(Date.now()),
      duration_seconds: 232,
      transcript,
      summary: claim.narrative,
      processing: 'done',
      ticket_id: claim.escalation_reason ? claim.id + 500 : undefined,
    }
    upsertCall(done)
    emit('call.completed', { call: done })
  })

  at(17_600, () => {
    if (claim.escalation_reason) {
      const ticket: Ticket = {
        id: claim.id + 500,
        claim_id: claim.id,
        call_id: callId,
        reference: `TCK-${claim.reference.slice(3)}`,
        severity: claim.risk.level,
        reasons: [...claim.weather_evidence.reasons.slice(0, 2), claim.escalation_reason],
        farmer_explanation: claim.farmer_explanation ?? '',
        status: 'open',
        created_at: iso(Date.now()),
        updated_at: iso(Date.now()),
      }
      state.tickets.unshift(ticket)
      emit('ticket.created', { ticket })
    } else {
      const file: EvidenceFile = {
        id: `up_${Math.random().toString(36).slice(2, 10)}`,
        item_key: 'field_photo_wide',
        filename: `IMG_${1000 + Math.floor(Math.random() * 8000)}.jpg`,
        content_type: 'image/jpeg',
        size: 1_840_221,
        uploaded_at: iso(Date.now()),
        client_time: iso(Date.now() - 30_000),
        lat: claim.location.lat,
        lon: claim.location.lon,
        url: mockPhoto(claim.id, 'field_photo_wide'),
        quality_flag: 'unchecked',
      }
      const idx = state.claims.findIndex((c) => c.id === claim.id)
      if (idx >= 0) {
        state.claims[idx] = {
          ...state.claims[idx],
          evidence_uploads: [...state.claims[idx].evidence_uploads, file],
        }
      }
      emit('evidence.uploaded', {
        claim_id: claim.id,
        claim_reference: claim.reference,
        file,
      })
    }
  })
}

function runMockEval() {
  const total = EVAL_REPORT.results.length
  EVAL_REPORT.results.forEach((res, i) => {
    at(600 * (i + 1), () =>
      emit('eval.progress', { done: i + 1, total, scenario: res.scenario, passed: res.passed }),
    )
  })
  at(600 * (total + 1), () => {
    state.evalReport = { ...EVAL_REPORT, run_id: `eval-${Date.now()}`, finished_at: iso(Date.now()) }
    emit('eval.completed', { report: state.evalReport })
  })
}

/* ------------------------------------------------------------------ *
 * MockSocket — same surface as WebSocket, no server needed
 * ------------------------------------------------------------------ */

let cycle: number | undefined

export class MockSocket {
  readyState = 0
  onopen: (() => void) | null = null
  onclose: (() => void) | null = null
  onerror: (() => void) | null = null
  onmessage: ((e: { data: string }) => void) | null = null
  private listener: Listener

  constructor(_url: string) {
    this.listener = (e) => this.onmessage?.({ data: JSON.stringify(e) })
    listeners.add(this.listener)
    window.setTimeout(() => {
      this.readyState = 1
      this.onopen?.()
      if (cycle === undefined) {
        window.setTimeout(runScenario, 2500)
        cycle = window.setInterval(runScenario, 20_000)
      }
    }, 260)
  }

  send(_data: string) {
    /* the mock stream ignores pings */
  }

  close() {
    this.readyState = 3
    listeners.delete(this.listener)
    this.onclose?.()
  }
}

export function stopMockStream() {
  if (cycle !== undefined) {
    window.clearInterval(cycle)
    cycle = undefined
  }
  timers.forEach((t) => window.clearTimeout(t))
}

/* ------------------------------------------------------------------ */

const MOCK_PROMPT = `# Sunil — Araxys Desk crop-insurance intake agent

You are Sunil, a calm, respectful voice assistant for a crop-insurance help desk.
You speak whatever language the caller speaks, including dialect and code-mixing.

## Absolute rules
1. You NEVER promise money, an approval, or a timeline. If asked, say what the
   process is and who decides, then continue the intake.
2. You only state facts that appear below, and you quote the fact id in your
   internal reasoning. If a fact is not below, say you do not have it and that a
   person will confirm it.
3. One question per turn. Confirm each answer before moving on.
4. If the caller is distressed, asks for a human, or the weather record does not
   match the claim, escalate and say why in plain language.

## Weather knowledge (snapshot, ${SNAPSHOT.days} days, ${SNAPSHOT.districts.length} districts)
Coverage rule: you may only speak about dates inside the snapshot window.
${SNAPSHOT.districts
  .slice(0, 3)
  .map(
    (d) =>
      `- ${d.name}: 60-day rain ${d.daily
        .reduce((n, x) => n + x.precipitation_mm, 0)
        .toFixed(0)} mm; notable — ${d.notable[0] ?? 'none'}`,
  )
  .join('\n')}
… (${SNAPSHOT.districts.length - 3} more districts)

## Scheme facts
${SCHEME_FACTS.map((f) => `[${f.fact_id}] ${f.text}`).join('\n')}

## Unknowns you must admit
- District-level sum insured and indemnity level
- Exact enrolment cut-off date for this season
- Whether a specific field is enrolled

## Safe scripts
payout_question → "I cannot tell you an amount. The amount is decided after a
field survey by the insurance company using the notified sum insured."
approval_question → "I cannot approve or reject anything. I record your claim
accurately and a surveyor decides."
timeline_question → "I cannot promise a date. What I can tell you is the next
step and who to contact."
escalation → say the reason in the caller's language, non-accusatory.
data_unavailable → "I could not reach the weather record, so a person will
verify this with you." Never say verified.

Reviewer transfer number: +91 89391 53390
Generated at: ${SNAPSHOT.generated_at}
`
