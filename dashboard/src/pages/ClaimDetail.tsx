import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { toast } from 'sonner'
import { ArrowLeft, Download, MessageSquare, Save, ScrollText } from 'lucide-react'
import type { ClaimStatus } from '@/types'
import { useCall, useClaim, usePatchClaim } from '@/lib/api'
import { CLAIM_STATUS_LABEL, CLAIM_STATUS_TONE, RISK_TONE, VERDICT_LABEL, VERDICT_TONE } from '@/lib/tone'
import { fmtDateTime, languageName, titleize } from '@/lib/utils'
import { Badge, Button, Chip, EmptyState, Panel, PanelHeader, Skeleton } from '@/components/ui/base'
import { TruthPanel } from '@/components/truth/TruthPanel'
import { TranscriptDrawer } from '@/components/truth/Transcript'

const NEXT_STATUS: ClaimStatus[] = ['logged', 'under_review', 'escalated', 'approved_for_survey', 'closed']

export default function ClaimDetail() {
  const { id } = useParams()
  const claimId = Number(id)
  const { data: claim, isLoading } = useClaim(claimId)
  const { data: call } = useCall(claim?.call_id)
  const patch = usePatchClaim()
  const [notes, setNotes] = useState('')
  const [transcriptOpen, setTranscriptOpen] = useState(false)

  useEffect(() => {
    if (claim) setNotes(claim.reviewer_notes ?? '')
  }, [claim?.id, claim?.reviewer_notes])

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-[92px] rounded-[13px]" />
        <Skeleton className="h-[160px] rounded-[13px]" />
        <Skeleton className="h-[420px] rounded-[13px]" />
      </div>
    )
  }

  if (!claim) {
    return (
      <Panel>
        <EmptyState
          icon={<ScrollText size={17} />}
          title="Claim not found"
          hint="It may have been cleared by a demo reset."
          action={
            <Link to="/claims" className="text-[13px] font-medium text-[var(--accent-fg)] hover:underline">
              Back to all claims
            </Link>
          }
        />
      </Panel>
    )
  }

  const exportJson = () => {
    const blob = new Blob([JSON.stringify(claim, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${claim.reference}.json`
    a.click()
    URL.revokeObjectURL(url)
    toast.success('Claim exported', { description: `${claim.reference}.json` })
  }

  const setStatus = (status: ClaimStatus) => {
    patch.mutate(
      { id: claim.id, status },
      { onSuccess: () => toast.success(`Status set to ${CLAIM_STATUS_LABEL[status]}`) },
    )
  }

  const saveNotes = () => {
    patch.mutate(
      { id: claim.id, reviewer_notes: notes },
      { onSuccess: () => toast.success('Reviewer notes saved') },
    )
  }

  return (
    <div className="space-y-4">
      {/* header */}
      <Panel className="px-5 py-4">
        <Link
          to="/claims"
          className="mb-3 inline-flex items-center gap-1.5 text-[12px] text-[var(--fg-subtle)] transition-colors hover:text-[var(--fg)]"
        >
          <ArrowLeft size={13} />
          All claims
        </Link>

        <div className="flex flex-wrap items-start gap-x-6 gap-y-3">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2.5">
              <h2 className="mono text-[24px] leading-none font-semibold tracking-[-0.03em]">
                {claim.reference}
              </h2>
              <Badge tone={CLAIM_STATUS_TONE[claim.status]} dot>
                {CLAIM_STATUS_LABEL[claim.status]}
              </Badge>
              <Badge tone={VERDICT_TONE[claim.weather_evidence.verdict]}>
                {VERDICT_LABEL[claim.weather_evidence.verdict]}
              </Badge>
              <Badge tone={RISK_TONE[claim.risk.level]} mono>
                risk {claim.risk.score}
              </Badge>
            </div>
            <p className="mt-2 max-w-3xl text-[12.5px] leading-relaxed text-[var(--fg-muted)]">
              {claim.narrative}
            </p>
            <div className="mono mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-[var(--fg-subtle)]">
              <span>{titleize(claim.crop)}</span>
              <span>{titleize(claim.damage_type)}</span>
              <span>
                {[claim.location.village, claim.location.taluk, claim.location.district]
                  .filter(Boolean)
                  .join(' · ')}
              </span>
              <span>{languageName(claim.farmer.language)}</span>
              <span>created {fmtDateTime(claim.created_at)}</span>
            </div>
          </div>

          <div className="ml-auto flex shrink-0 items-center gap-2">
            <Button icon={<MessageSquare size={14} />} onClick={() => setTranscriptOpen(true)}>
              Transcript
            </Button>
            <Button icon={<Download size={14} />} onClick={exportJson}>
              Export JSON
            </Button>
          </div>
        </div>
      </Panel>

      {/* reviewer controls */}
      <Panel>
        <PanelHeader eyebrow="Reviewer" title="Status & notes" icon={<Save size={14} />} tone="warn" />
        <div className="grid gap-4 px-5 pb-5 lg:grid-cols-[1fr_1.4fr]">
          <div>
            <div className="eyebrow mb-2">Move this claim to</div>
            <div className="flex flex-wrap gap-1.5">
              {NEXT_STATUS.map((s) => (
                <Chip
                  key={s}
                  active={claim.status === s}
                  onClick={() => setStatus(s)}
                  disabled={patch.isPending || claim.status === s}
                >
                  {CLAIM_STATUS_LABEL[s]}
                </Chip>
              ))}
            </div>
            <p className="mt-3 text-[11.5px] leading-relaxed text-[var(--fg-subtle)]">
              A reviewer decision never overwrites the machine verdict — the weather check, citations and
              risk signals above stay exactly as the pipeline recorded them.
            </p>
          </div>

          <div>
            <div className="eyebrow mb-2">Reviewer notes</div>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={4}
              placeholder="What did you check, who did you call, what happens next…"
              className="w-full resize-y rounded-[10px] border px-3 py-2.5 text-[12.5px] leading-relaxed outline-none placeholder:text-[var(--fg-subtle)] focus:border-[var(--accent-line)]"
              style={{ background: 'var(--surface-inset)', borderColor: 'var(--line)', color: 'var(--fg)' }}
            />
            <div className="mt-2 flex items-center gap-2">
              <Button
                variant="primary"
                icon={<Save size={14} />}
                onClick={saveNotes}
                disabled={patch.isPending || notes === (claim.reviewer_notes ?? '')}
              >
                Save notes
              </Button>
              <span className="text-[11px] text-[var(--fg-subtle)]">
                updated {fmtDateTime(claim.updated_at)}
              </span>
            </div>
          </div>
        </div>
      </Panel>

      <TruthPanel claim={claim} call={call} layout="grid" showTranscriptButton={false} />

      <TranscriptDrawer open={transcriptOpen} onOpenChange={setTranscriptOpen} call={call} />
    </div>
  )
}
