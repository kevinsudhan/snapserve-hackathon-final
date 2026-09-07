import { create } from 'zustand'
import type { CallRecord, Claim, LiveEvent, Ticket } from '@/types'

export type WsStatus = 'idle' | 'connecting' | 'open' | 'reconnecting' | 'closed'

type LiveState = {
  status: WsStatus
  lastEventAt?: string
  events: LiveEvent[]
  /** claims as they stream in, keyed by claim id — the Truth Panel animates off this */
  claims: Record<number, Claim>
  calls: Record<number, CallRecord>
  tickets: Record<number, Ticket>
  activeCallId?: number
  selectedCallId?: number
  /** claim id → set of section keys that have arrived, used for reveal animations */
  revealed: Record<number, string[]>

  setStatus: (s: WsStatus) => void
  push: (e: LiveEvent) => void
  selectCall: (id?: number) => void
  reset: () => void
}

const MAX_EVENTS = 80

function reveal(prev: string[] | undefined, claim: Claim): string[] {
  const keys = new Set(prev ?? [])
  keys.add('intake')
  if (claim.location.resolution_confidence > 0) keys.add('location')
  if (claim.weather_evidence.daily.length) keys.add('weather')
  if (claim.disaster_evidence.events.length) keys.add('disasters')
  if (claim.crop_evidence) keys.add('crop')
  if (claim.scheme_matches.length) keys.add('schemes')
  if (claim.risk.signals.length) keys.add('risk')
  if (claim.escalation_reason) keys.add('escalation')
  if (claim.evidence_required.length) keys.add('evidence')
  return [...keys]
}

export const useLive = create<LiveState>((set) => ({
  status: 'idle',
  events: [],
  claims: {},
  calls: {},
  tickets: {},
  revealed: {},

  setStatus: (status) => set({ status }),

  selectCall: (selectedCallId) => set({ selectedCallId }),

  reset: () =>
    set({ events: [], claims: {}, calls: {}, tickets: {}, revealed: {}, activeCallId: undefined }),

  push: (e) =>
    set((s) => {
      const next: Partial<LiveState> = {
        events: [e, ...s.events].slice(0, MAX_EVENTS),
        lastEventAt: e.at,
      }
      const p = e.payload as {
        call?: CallRecord
        claim?: Claim
        ticket?: Ticket
        claim_id?: number
        file?: unknown
      }

      if (p.call) {
        next.calls = { ...s.calls, [p.call.id]: p.call }
        if (e.type === 'call.started') {
          next.activeCallId = p.call.id
          next.selectedCallId = p.call.id
        }
        if (e.type === 'call.completed' && s.activeCallId === p.call.id) {
          next.activeCallId = undefined
        }
      }

      if (p.claim) {
        next.claims = { ...s.claims, [p.claim.id]: p.claim }
        next.revealed = { ...s.revealed, [p.claim.id]: reveal(s.revealed[p.claim.id], p.claim) }
      }

      if (p.ticket) {
        next.tickets = { ...s.tickets, [p.ticket.id]: p.ticket }
      }

      return next
    }),
}))

export const selectLiveClaimForCall = (callId?: number) => (s: LiveState) => {
  if (!callId) return undefined
  return Object.values(s.claims).find((c) => c.call_id === callId)
}
