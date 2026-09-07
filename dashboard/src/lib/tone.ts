import type { Tone } from '@/components/ui/base'
import type { ClaimStatus, TicketStatus, Verdict } from '@/types'

export const VERDICT_LABEL: Record<Verdict, string> = {
  supported: 'Supported',
  partially_supported: 'Partially supported',
  not_supported: 'Not supported',
  unverifiable: 'Unverifiable',
}

export const VERDICT_TONE: Record<Verdict, Tone> = {
  supported: 'ok',
  partially_supported: 'warn',
  not_supported: 'danger',
  unverifiable: 'neutral',
}

export const VERDICT_BLURB: Record<Verdict, string> = {
  supported: 'The weather record matches what the farmer described.',
  partially_supported: 'Part of the claimed window clears the threshold, part does not.',
  not_supported: 'The weather record does not match the claimed event.',
  unverifiable: 'The data source cannot confirm or deny this — never recorded as verified.',
}

export const RISK_TONE = { low: 'ok', medium: 'warn', high: 'danger' } as const

export const CLAIM_STATUS_LABEL: Record<ClaimStatus, string> = {
  logged: 'Logged',
  escalated: 'Escalated',
  under_review: 'Under review',
  approved_for_survey: 'Approved for survey',
  closed: 'Closed',
}

export const CLAIM_STATUS_TONE: Record<ClaimStatus, Tone> = {
  logged: 'accent',
  escalated: 'danger',
  under_review: 'warn',
  approved_for_survey: 'sky',
  closed: 'neutral',
}

export const TICKET_STATUS_LABEL: Record<TicketStatus, string> = {
  open: 'Open',
  in_review: 'In review',
  resolved: 'Resolved',
  rejected: 'Rejected',
}

export const TICKET_STATUS_TONE: Record<TicketStatus, Tone> = {
  open: 'danger',
  in_review: 'warn',
  resolved: 'ok',
  rejected: 'neutral',
}

export const CITATION_TONE: Record<string, Tone> = {
  scheme: 'teal',
  weather: 'sky',
  disaster: 'violet',
  crop: 'accent',
  gazetteer: 'neutral',
  other: 'neutral',
}

export function alertTone(level: string): Tone {
  const l = level.toLowerCase()
  if (l === 'red') return 'danger'
  if (l === 'orange') return 'warn'
  if (l === 'green') return 'ok'
  return 'violet'
}
