import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseQueryOptions,
} from '@tanstack/react-query'
import type {
  CallRecord,
  Citation,
  Claim,
  ClaimStatus,
  EvalReport,
  EvidenceFile,
  EvidenceLink,
  EvidencePortal,
  GeoCollection,
  Health,
  KnowledgeStatus,
  Stats,
  Ticket,
  TicketStatus,
  WeatherSnapshot,
} from '@/types'
import { MOCK } from './utils'

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
    this.name = 'ApiError'
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const doFetch = MOCK
    ? (await import('./mock/server')).mockFetch
    : (p: string, i?: RequestInit) => fetch(p, i)

  const res = await doFetch(path, init)
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = (await res.json()) as { detail?: string }
      if (body?.detail) detail = body.detail
    } catch {
      /* keep statusText */
    }
    throw new ApiError(res.status, detail)
  }
  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}

const jsonInit = (method: string, body?: unknown): RequestInit => ({
  method,
  headers: { 'content-type': 'application/json' },
  body: body === undefined ? undefined : JSON.stringify(body),
})

/* ------------------------------------------------------------------ *
 * query keys
 * ------------------------------------------------------------------ */

export const qk = {
  health: ['health'] as const,
  stats: ['stats'] as const,
  calls: (limit = 50) => ['calls', limit] as const,
  call: (id: number) => ['call', id] as const,
  claims: (status?: string, q?: string) => ['claims', status ?? '', q ?? ''] as const,
  claim: (id: number) => ['claim', id] as const,
  tickets: (status?: string) => ['tickets', status ?? ''] as const,
  knowledge: ['knowledge', 'status'] as const,
  snapshot: ['knowledge', 'snapshot'] as const,
  geo: ['knowledge', 'geo'] as const,
  prompt: ['knowledge', 'prompt'] as const,
  citation: (id: string) => ['citation', id] as const,
  evalLatest: ['eval', 'latest'] as const,
  portal: (token: string) => ['evidence', token] as const,
}

/* ------------------------------------------------------------------ *
 * queries
 * ------------------------------------------------------------------ */

type Opts<T> = Omit<UseQueryOptions<T, Error, T>, 'queryKey' | 'queryFn'>

export function useHealth(opts?: Opts<Health>) {
  return useQuery({
    queryKey: qk.health,
    queryFn: () => request<Health>('/api/health'),
    refetchInterval: 15_000,
    ...opts,
  })
}

export function useStats(opts?: Opts<Stats>) {
  return useQuery({
    queryKey: qk.stats,
    queryFn: () => request<Stats>('/api/stats'),
    ...opts,
  })
}

export function useCalls(limit = 50) {
  return useQuery({
    queryKey: qk.calls(limit),
    queryFn: () => request<CallRecord[]>(`/api/calls?limit=${limit}`),
  })
}

export function useCall(id?: number) {
  return useQuery({
    queryKey: qk.call(id ?? 0),
    queryFn: () => request<CallRecord>(`/api/calls/${id}`),
    enabled: typeof id === 'number' && id > 0,
  })
}

export function useClaims(status?: string, q?: string) {
  const params = new URLSearchParams()
  if (status) params.set('status', status)
  if (q) params.set('q', q)
  const suffix = params.toString() ? `?${params}` : ''
  return useQuery({
    queryKey: qk.claims(status, q),
    queryFn: () => request<Claim[]>(`/api/claims${suffix}`),
  })
}

export function useClaim(id?: number) {
  return useQuery({
    queryKey: qk.claim(id ?? 0),
    queryFn: () => request<Claim>(`/api/claims/${id}`),
    enabled: typeof id === 'number' && id > 0,
  })
}

export function useTickets(status?: string) {
  return useQuery({
    queryKey: qk.tickets(status),
    queryFn: () => request<Ticket[]>(`/api/tickets${status ? `?status=${status}` : ''}`),
  })
}

export function useKnowledgeStatus() {
  return useQuery({
    queryKey: qk.knowledge,
    queryFn: () => request<KnowledgeStatus>('/api/knowledge/status'),
  })
}

export function useSnapshot() {
  return useQuery({
    queryKey: qk.snapshot,
    queryFn: () => request<WeatherSnapshot>('/api/knowledge/snapshot'),
    staleTime: 5 * 60_000,
  })
}

export function useGeo() {
  return useQuery({
    queryKey: qk.geo,
    queryFn: () => request<GeoCollection>('/api/knowledge/geo'),
    staleTime: Infinity,
  })
}

export function usePrompt(enabled = false) {
  return useQuery({
    queryKey: qk.prompt,
    queryFn: () => request<{ system_prompt: string; approx_tokens: number }>('/api/knowledge/prompt'),
    enabled,
    staleTime: 5 * 60_000,
  })
}

export function useCitation(id?: string) {
  return useQuery({
    queryKey: qk.citation(id ?? ''),
    queryFn: () => request<Citation>(`/api/citations/${encodeURIComponent(id ?? '')}`),
    enabled: Boolean(id),
    staleTime: Infinity,
  })
}

export function useEvalLatest() {
  return useQuery({
    queryKey: qk.evalLatest,
    queryFn: () => request<EvalReport | null>('/api/eval/latest'),
  })
}

export function useEvidencePortal(token?: string) {
  return useQuery({
    queryKey: qk.portal(token ?? ''),
    queryFn: () => request<EvidencePortal>(`/api/evidence/${token}`),
    enabled: Boolean(token),
    retry: 1,
  })
}

/* ------------------------------------------------------------------ *
 * mutations
 * ------------------------------------------------------------------ */

export function usePatchClaim() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({
      id,
      ...body
    }: {
      id: number
      status?: ClaimStatus
      reviewer_notes?: string
    }) => request<Claim>(`/api/claims/${id}`, jsonInit('PATCH', body)),
    onSuccess: (claim) => {
      qc.setQueryData(qk.claim(claim.id), claim)
      void qc.invalidateQueries({ queryKey: ['claims'] })
      void qc.invalidateQueries({ queryKey: qk.stats })
    },
  })
}

export function usePatchTicket() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({
      id,
      ...body
    }: {
      id: number
      status?: TicketStatus
      reviewer_notes?: string
    }) => request<Ticket>(`/api/tickets/${id}`, jsonInit('PATCH', body)),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['tickets'] })
      void qc.invalidateQueries({ queryKey: qk.stats })
    },
  })
}

export function useEvidenceLink() {
  return useMutation({
    mutationFn: (claimId: number) =>
      request<EvidenceLink>(`/api/claims/${claimId}/evidence-link`, jsonInit('POST')),
  })
}

export function useRefreshKnowledge() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => request<KnowledgeStatus>('/api/knowledge/refresh', jsonInit('POST')),
    onSuccess: (status) => {
      qc.setQueryData(qk.knowledge, status)
      void qc.invalidateQueries({ queryKey: qk.snapshot })
      void qc.invalidateQueries({ queryKey: qk.prompt })
    },
  })
}

export function useUploadEvidence(token: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (input: {
      itemKey: string
      file: File
      lat?: number
      lon?: number
      onProgress?: (fraction: number) => void
    }) => {
      const form = new FormData()
      form.set('item_key', input.itemKey)
      form.set('file', input.file)
      form.set('client_time', new Date().toISOString())
      if (input.lat != null) form.set('lat', String(input.lat))
      if (input.lon != null) form.set('lon', String(input.lon))

      if (MOCK) {
        for (const f of [0.15, 0.4, 0.7, 0.92, 1]) {
          await new Promise((r) => setTimeout(r, 130))
          input.onProgress?.(f)
        }
        const { mockFetch } = await import('./mock/server')
        const res = await mockFetch(`/api/evidence/${token}/upload`, {
          method: 'POST',
          body: form,
        })
        return (await res.json()) as EvidenceFile
      }

      return new Promise<EvidenceFile>((resolve, reject) => {
        const xhr = new XMLHttpRequest()
        xhr.open('POST', `/api/evidence/${token}/upload`)
        xhr.upload.onprogress = (e) => {
          if (e.lengthComputable) input.onProgress?.(e.loaded / e.total)
        }
        xhr.onload = () => {
          if (xhr.status >= 200 && xhr.status < 300) {
            resolve(JSON.parse(xhr.responseText) as EvidenceFile)
          } else {
            reject(new ApiError(xhr.status, xhr.statusText))
          }
        }
        xhr.onerror = () => reject(new ApiError(0, 'network error'))
        xhr.send(form)
      })
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: qk.portal(token) })
    },
  })
}

export function useSetDataDown() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (enabled: boolean) =>
      request<{ enabled: boolean }>('/api/admin/data-down', jsonInit('POST', { enabled })),
    onSuccess: () => void qc.invalidateQueries({ queryKey: qk.health }),
  })
}

export function useRunEval() {
  return useMutation({
    mutationFn: (body?: { scenarios?: string[]; n?: number }) =>
      request<{ started: boolean }>('/api/eval/run', jsonInit('POST', body ?? {})),
  })
}

export function useSimulateCall() {
  return useMutation({
    mutationFn: (body: { transcript: string; from_number?: string; language?: string }) =>
      request<CallRecord>('/api/admin/simulate', jsonInit('POST', body)),
  })
}

export { request as apiRequest }
