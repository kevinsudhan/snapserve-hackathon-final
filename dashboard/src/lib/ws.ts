import type { QueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import type { CallRecord, Claim, LiveEvent, Ticket } from '@/types'
import { useLive } from '@/store/live'
import { qk } from './api'
import { MOCK, languageName, titleize } from './utils'

type SocketLike = {
  readyState: number
  onopen: (() => void) | null
  onclose: (() => void) | null
  onerror: (() => void) | null
  onmessage: ((e: { data: string }) => void) | null
  send: (data: string) => void
  close: () => void
}

let socket: SocketLike | null = null
let opening = false
let generation = 0
let retry = 0
let retryTimer: number | undefined
let pingTimer: number | undefined
let disposed = false

function wsUrl() {
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
  return `${proto}://${window.location.host}/ws/events`
}

async function open(qc: QueryClient) {
  if (opening) return
  const gen = ++generation
  opening = true
  const { setStatus, push } = useLive.getState()
  setStatus(retry === 0 ? 'connecting' : 'reconnecting')

  let next: SocketLike
  if (MOCK) {
    const { MockSocket } = await import('./mock/server')
    next = new MockSocket(wsUrl()) as unknown as SocketLike
  } else {
    next = new WebSocket(wsUrl()) as unknown as SocketLike
  }
  // a remount raced us while the dynamic import resolved — this socket is stale
  if (disposed || gen !== generation) {
    next.close()
    return
  }
  opening = false
  socket = next

  socket.onopen = () => {
    retry = 0
    setStatus('open')
    pingTimer = window.setInterval(() => {
      try {
        socket?.send(JSON.stringify({ type: 'ping' }))
      } catch {
        /* socket already gone */
      }
    }, 25_000)
  }

  socket.onmessage = (raw) => {
    let event: LiveEvent
    try {
      event = JSON.parse(raw.data) as LiveEvent
    } catch {
      return
    }
    if (!event?.type) return
    push(event)
    handle(event, qc)
  }

  socket.onerror = () => {
    /* onclose does the reconnect work */
  }

  socket.onclose = () => {
    window.clearInterval(pingTimer)
    if (disposed) {
      setStatus('closed')
      return
    }
    setStatus('reconnecting')
    const delay = Math.min(12_000, 700 * 2 ** retry)
    retry += 1
    retryTimer = window.setTimeout(() => void open(qc), delay)
  }
}

function handle(event: LiveEvent, qc: QueryClient) {
  const p = event.payload as {
    call?: CallRecord
    claim?: Claim
    ticket?: Ticket
    claim_reference?: string
    status?: unknown
    done?: number
    total?: number
  }

  switch (event.type) {
    case 'call.started':
      void qc.invalidateQueries({ queryKey: ['calls'] })
      toast('Incoming call', {
        description: `${p.call?.from_number ?? 'Unknown number'} · ${languageName(
          p.call?.language_detected,
        )}`,
      })
      break

    case 'call.completed':
      void qc.invalidateQueries({ queryKey: ['calls'] })
      void qc.invalidateQueries({ queryKey: qk.stats })
      break

    case 'claim.created':
      void qc.invalidateQueries({ queryKey: ['claims'] })
      void qc.invalidateQueries({ queryKey: qk.stats })
      toast.success('Claim opened', { description: p.claim?.reference })
      break

    case 'claim.updated':
      if (p.claim) qc.setQueryData(qk.claim(p.claim.id), p.claim)
      void qc.invalidateQueries({ queryKey: ['claims'] })
      break

    case 'ticket.created':
      void qc.invalidateQueries({ queryKey: ['tickets'] })
      void qc.invalidateQueries({ queryKey: qk.stats })
      toast.warning('Escalated to a person', {
        description: `${p.ticket?.reference ?? ''} · ${titleize(p.ticket?.severity)} severity`,
      })
      break

    case 'ticket.updated':
      void qc.invalidateQueries({ queryKey: ['tickets'] })
      break

    case 'evidence.uploaded':
      void qc.invalidateQueries({ queryKey: ['claims'] })
      void qc.invalidateQueries({ queryKey: ['evidence'] })
      toast('Evidence received', { description: p.claim_reference })
      break

    case 'knowledge.refreshed':
      void qc.invalidateQueries({ queryKey: ['knowledge'] })
      toast.success('Knowledge snapshot refreshed and pushed to the agent')
      break

    case 'guardrail.incident':
      void qc.invalidateQueries({ queryKey: ['calls'] })
      toast.error('Guardrail incident', { description: 'Review the call transcript' })
      break

    case 'eval.completed':
      void qc.invalidateQueries({ queryKey: qk.evalLatest })
      toast.success('Eval run finished')
      break

    case 'poller.status':
      void qc.invalidateQueries({ queryKey: qk.health })
      break

    default:
      break
  }
}

export function connectLive(qc: QueryClient) {
  disposed = false
  if (socket || opening) return
  void open(qc)
}

export function disconnectLive() {
  disposed = true
  opening = false
  generation += 1
  window.clearTimeout(retryTimer)
  window.clearInterval(pingTimer)
  socket?.close()
  socket = null
  retry = 0
}
