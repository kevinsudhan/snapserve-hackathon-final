import { forwardRef, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import { ArrowUpRight, PhoneCall, PhoneIncoming, Radio, ScrollText } from 'lucide-react'
import type { CallRecord, Claim } from '@/types'
import { useCalls, useClaims } from '@/lib/api'
import { CLAIM_STATUS_LABEL, CLAIM_STATUS_TONE, VERDICT_LABEL, VERDICT_TONE } from '@/lib/tone'
import { ago, cn, duration, languageName, titleize } from '@/lib/utils'
import { useLive } from '@/store/live'
import {
  Badge,
  EmptyState,
  LiveDot,
  Panel,
  PanelHeader,
  Skeleton,
  toneVars,
} from '@/components/ui/base'
import { Waveform } from '@/components/live/Waveform'
import { TruthPanel } from '@/components/truth/TruthPanel'
import { TranscriptBody } from '@/components/truth/Transcript'

export default function LiveDesk() {
  const { data: fetchedCalls, isLoading } = useCalls(24)
  const { data: fetchedClaims } = useClaims()
  const liveCalls = useLive((s) => s.calls)
  const liveClaims = useLive((s) => s.claims)
  const activeCallId = useLive((s) => s.activeCallId)
  const selectedCallId = useLive((s) => s.selectedCallId)
  const selectCall = useLive((s) => s.selectCall)

  /** live store wins over the polled list — it is always the newest state */
  const calls = useMemo(() => {
    const map = new Map<number, CallRecord>()
    for (const c of fetchedCalls ?? []) map.set(c.id, c)
    for (const c of Object.values(liveCalls)) map.set(c.id, c)
    return [...map.values()].sort((a, b) => +new Date(b.started_at) - +new Date(a.started_at))
  }, [fetchedCalls, liveCalls])

  const selected = useMemo(
    () => calls.find((c) => c.id === selectedCallId) ?? calls.find((c) => c.id === activeCallId) ?? calls[0],
    [calls, selectedCallId, activeCallId],
  )

  const claim: Claim | undefined = useMemo(() => {
    if (!selected) return undefined
    const live = Object.values(liveClaims).find((c) => c.call_id === selected.id)
    if (live) return live
    return (fetchedClaims ?? []).find((c) => c.id === selected.claim_id || c.call_id === selected.id)
  }, [selected, liveClaims, fetchedClaims])

  const active = calls.find((c) => c.status === 'in_progress')

  return (
    <div className="grid grid-cols-1 items-start gap-4 xl:grid-cols-[minmax(320px,380px)_1fr]">
      {/* ------- left rail ------- */}
      <div className="space-y-4 xl:sticky xl:top-4">
        {active ? <ActiveCallCard key={active.id} call={active} /> : <IdleCard key="idle" />}

        <Panel>
          <PanelHeader
            eyebrow="Poller"
            title="Recent calls"
            icon={<PhoneCall size={14} />}
            tone="sky"
            right={<Badge tone="neutral" mono>{calls.length}</Badge>}
          />
          <div className="max-h-[calc(100dvh-420px)] min-h-[220px] overflow-y-auto px-2.5 pb-3">
            {isLoading && calls.length === 0
              ? Array.from({ length: 5 }).map((_, i) => (
                  <Skeleton key={i} className="mb-1.5 h-[62px] rounded-[10px]" />
                ))
              : calls.map((c) => (
                  <CallRow
                    key={c.id}
                    call={c}
                    selected={selected?.id === c.id}
                    onSelect={() => selectCall(c.id)}
                  />
                ))}
            {!isLoading && calls.length === 0 && (
              <EmptyState
                icon={<PhoneIncoming size={17} />}
                title="No calls yet"
                hint="Ring +91 79658 54267 and this list fills in within seconds."
              />
            )}
          </div>
        </Panel>
      </div>

      {/* ------- truth panel ------- */}
      <div className="min-w-0 space-y-4">
        {claim ? (
          <>
            <ClaimHeadline claim={claim} call={selected} />
            <TruthPanel claim={claim} call={selected} layout="stack" showTranscriptButton={false} />
            <Panel>
              <PanelHeader
                eyebrow="Step 8"
                title="Transcript"
                icon={<ScrollText size={14} />}
                tone="neutral"
              />
              <div className="max-h-[520px] overflow-hidden">
                <TranscriptBody call={selected} />
              </div>
            </Panel>
          </>
        ) : (
          <Panel>
            <EmptyState
              icon={<Radio size={18} />}
              tone="accent"
              title="The truth panel builds itself here"
              hint="Pick a call on the left, or wait for the next one — intake facts, the weather check, disaster events, scheme citations and the risk score all animate in as the pipeline resolves them."
              className="py-24"
            />
          </Panel>
        )}
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ */

const ActiveCallCard = forwardRef<HTMLDivElement, { call: CallRecord }>(function ActiveCallCard(
  { call },
  ref,
) {
  const [elapsed, setElapsed] = useState(() => Math.max(0, (Date.now() - +new Date(call.started_at)) / 1000))

  useEffect(() => {
    const t = window.setInterval(
      () => setElapsed(Math.max(0, (Date.now() - +new Date(call.started_at)) / 1000)),
      1000,
    )
    return () => window.clearInterval(t)
  }, [call.started_at])

  return (
    <motion.div
      ref={ref}
      initial={{ opacity: 0, y: 10, scale: 0.99 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: -8 }}
      transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
    >
      <Panel className="relative overflow-hidden" style={{ borderColor: 'var(--accent-line)' }}>
        <span
          className="pointer-events-none absolute inset-0"
          style={{ background: 'radial-gradient(320px 130px at 50% 0%, var(--accent-soft), transparent)' }}
          aria-hidden
        />
        <div className="relative px-5 pt-4 pb-4">
          <div className="mb-3 flex items-center gap-2">
            <Badge tone="accent" dot>
              <LiveDot />
              In progress
            </Badge>
            <span className="mono ml-auto text-[13px] font-semibold tabular-nums">
              {duration(elapsed)}
            </span>
          </div>

          <div className="mono text-[18px] leading-none font-semibold tracking-[-0.02em]">
            {call.from_number ?? 'Unknown number'}
          </div>
          <div className="mt-1.5 flex flex-wrap items-center gap-2 text-[11.5px] text-[var(--fg-subtle)]">
            <span>{titleize(call.direction)}</span>
            <span aria-hidden>·</span>
            <span>{languageName(call.language_detected)}</span>
            {call.code_switching && (
              <>
                <span aria-hidden>·</span>
                <span className="text-[var(--violet)]">code-switching</span>
              </>
            )}
          </div>

          <div className="mt-4 flex items-end justify-center">
            <Waveform active bars={38} height={46} />
          </div>

          <div className="mt-4 flex items-center gap-2 text-[11.5px] text-[var(--fg-subtle)]">
            <span
              className="inline-block size-1.5 rounded-full"
              style={{ background: 'var(--accent-hi)' }}
            />
            {call.transcript.length > 0
              ? `${call.transcript.length} turns transcribed`
              : 'Waiting for the first turn…'}
            <span className="mono ml-auto">{call.snapserve_call_id}</span>
          </div>
        </div>
      </Panel>
    </motion.div>
  )
})

const IdleCard = forwardRef<HTMLDivElement>(function IdleCard(_props, ref) {
  return (
    <motion.div
      ref={ref}
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -8 }}
      transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
    >
      <Panel className="relative overflow-hidden px-5 py-5">
        <div className="mb-3 flex items-center gap-2">
          <Badge tone="neutral">Idle</Badge>
          <span className="ml-auto text-[11.5px] text-[var(--fg-subtle)]">line open</span>
        </div>
        <div className="mono text-[17px] leading-none font-semibold tracking-[-0.02em] text-[var(--fg-muted)]">
          +91 79658 54267
        </div>
        <p className="mt-2 text-[12px] leading-relaxed text-[var(--fg-subtle)]">
          Sunil is waiting for a call. The desk polls SnapServe every 3 seconds; the moment a call
          completes, the truth check runs and this panel fills in.
        </p>
        <div className="mt-4 opacity-45">
          <Waveform active={false} bars={38} height={40} />
        </div>
      </Panel>
    </motion.div>
  )
})

function CallRow({
  call,
  selected,
  onSelect,
}: {
  call: CallRecord
  selected: boolean
  onSelect: () => void
}) {
  const live = call.status === 'in_progress'
  return (
    <button
      onClick={onSelect}
      className={cn(
        'relative mb-1 flex w-full items-center gap-3 rounded-[10px] border px-3 py-2.5 text-left transition-colors duration-150',
        selected
          ? 'border-[var(--line-strong)] bg-[var(--surface-3)]'
          : 'border-transparent hover:border-[var(--line)] hover:bg-[var(--surface-2)]',
      )}
    >
      {selected && (
        <motion.span
          layoutId="call-active"
          className="absolute top-2 bottom-2 left-0 w-[2px] rounded-full"
          style={{ background: 'var(--accent-hi)' }}
        />
      )}
      <span
        className="grid size-7 shrink-0 place-items-center rounded-[8px] border"
        style={{
          background: live ? 'var(--accent-soft)' : 'var(--surface-inset)',
          borderColor: live ? 'var(--accent-line)' : 'var(--line)',
          color: live ? 'var(--accent-fg)' : 'var(--fg-subtle)',
        }}
      >
        {live ? <LiveDot /> : <PhoneCall size={13} />}
      </span>
      <span className="min-w-0 flex-1">
        <span className="mono block truncate text-[12.5px] font-medium">
          {call.from_number ?? 'Unknown'}
        </span>
        <span className="block truncate text-[11px] text-[var(--fg-subtle)]">
          {languageName(call.language_detected)} · {ago(call.started_at)}
        </span>
      </span>
      <span className="mono shrink-0 text-[11px] text-[var(--fg-subtle)]">
        {live ? 'live' : duration(call.duration_seconds)}
      </span>
    </button>
  )
}

function ClaimHeadline({ claim, call }: { claim: Claim; call?: CallRecord }) {
  const v = claim.weather_evidence.verdict
  const hasVerdict = claim.weather_evidence.daily.length > 0
  return (
    <Panel className="flex flex-wrap items-center gap-x-5 gap-y-3 px-5 py-3.5">
      <div className="min-w-0">
        <div className="eyebrow mb-1">Claim</div>
        <div className="flex items-center gap-2">
          <span className="mono text-[16px] font-semibold tracking-[-0.02em]">{claim.reference}</span>
          <Badge tone={CLAIM_STATUS_TONE[claim.status]} dot>
            {CLAIM_STATUS_LABEL[claim.status]}
          </Badge>
        </div>
      </div>

      <div className="hidden h-8 w-px sm:block" style={{ background: 'var(--line)' }} />

      <div className="min-w-0">
        <div className="eyebrow mb-1">Weather verdict</div>
        {hasVerdict ? (
          <span
            className="text-[14px] font-semibold"
            style={{ color: toneVars[VERDICT_TONE[v]].fg }}
          >
            {VERDICT_LABEL[v]}
          </span>
        ) : (
          <span className="text-[13px] text-[var(--fg-subtle)]">checking…</span>
        )}
      </div>

      <div className="hidden h-8 w-px sm:block" style={{ background: 'var(--line)' }} />

      <div className="min-w-0">
        <div className="eyebrow mb-1">Call</div>
        <span className="mono text-[13px]">
          {call ? duration(call.duration_seconds) : '—'}
          <span className="ml-2 text-[var(--fg-subtle)]">{languageName(claim.farmer.language)}</span>
        </span>
      </div>

      <Link
        to={`/claims/${claim.id}`}
        className="ml-auto inline-flex h-8 items-center gap-1.5 rounded-[8px] border px-3 text-[13px] font-medium text-[var(--fg-muted)] transition-colors duration-150 hover:bg-[var(--surface-3)] hover:text-[var(--fg)]"
        style={{ borderColor: 'var(--line-strong)' }}
      >
        Open full claim
        <ArrowUpRight size={13} />
      </Link>
    </Panel>
  )
}
