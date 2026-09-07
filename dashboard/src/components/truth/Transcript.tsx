import { motion } from 'framer-motion'
import { Bot, MessageSquare, ShieldCheck, TriangleAlert, User } from 'lucide-react'
import type { CallRecord } from '@/types'
import { cn, languageName, titleize } from '@/lib/utils'
import { Badge, EmptyState, toneVars } from '@/components/ui/base'
import { Drawer } from '@/components/ui/overlays'

export function TranscriptBody({ call }: { call?: CallRecord }) {
  if (!call) {
    return (
      <EmptyState
        icon={<MessageSquare size={17} />}
        title="No transcript yet"
        hint="Turns appear as SnapServe streams them into the ingest pipeline."
      />
    )
  }

  const incidents = call.guardrail_incidents
  const flagged = new Map(incidents.map((i) => [i.turn_index, i]))

  return (
    <div className="flex h-full flex-col">
      <div
        className="flex flex-wrap items-center gap-2 px-5 py-3"
        style={{ borderBottom: '1px solid var(--line)' }}
      >
        <Badge tone="neutral" mono>
          {call.transcript.length} turns
        </Badge>
        {(call.languages ?? []).map((l) => (
          <Badge key={l} tone="sky">
            {languageName(l)}
          </Badge>
        ))}
        {call.code_switching && <Badge tone="violet">code-switching</Badge>}
        <span className="ml-auto">
          {incidents.length === 0 ? (
            <Badge tone="ok" dot>
              <ShieldCheck size={11} />0 guardrail incidents
            </Badge>
          ) : (
            <Badge tone="danger" dot>
              {incidents.length} guardrail{incidents.length === 1 ? '' : 's'}
            </Badge>
          )}
        </span>
      </div>

      {incidents.length === 0 && call.transcript.length > 0 && (
        <div
          className="mx-5 mt-4 flex items-center gap-3 rounded-[11px] border px-3.5 py-3"
          style={{ background: 'var(--ok-soft)', borderColor: toneVars.ok.line }}
        >
          <ShieldCheck size={16} className="shrink-0 text-[var(--ok)]" />
          <p className="text-[12.5px] leading-snug text-[var(--fg-muted)]">
            <span className="font-semibold text-[var(--fg)]">Clean call.</span> No payout, approval or
            timeline promise; no invented scheme fact; the escalation rule fired where it should.
          </p>
        </div>
      )}

      <div className="min-h-0 flex-1 space-y-2.5 overflow-y-auto px-5 py-4">
        {call.transcript.map((turn, i) => {
          const incident = flagged.get(turn.i)
          const isAgent = turn.role === 'agent'
          return (
            <motion.div
              key={turn.i}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.22, delay: Math.min(i * 0.02, 0.3) }}
              className={cn('flex gap-2.5', isAgent ? '' : 'flex-row-reverse')}
            >
              <span
                className="mt-0.5 grid size-6 shrink-0 place-items-center rounded-full border"
                style={{
                  background: isAgent ? 'var(--accent-soft)' : 'var(--surface-3)',
                  borderColor: isAgent ? 'var(--accent-line)' : 'var(--line-strong)',
                  color: isAgent ? 'var(--accent-fg)' : 'var(--fg-muted)',
                }}
              >
                {isAgent ? <Bot size={12} /> : <User size={12} />}
              </span>

              <div className={cn('min-w-0 max-w-[86%]', isAgent ? '' : 'text-right')}>
                <div
                  className={cn(
                    'inline-block rounded-[11px] border px-3 py-2 text-left text-[12.5px] leading-relaxed',
                  )}
                  style={{
                    background: incident
                      ? 'var(--danger-soft)'
                      : isAgent
                        ? 'var(--surface-2)'
                        : 'var(--surface-inset)',
                    borderColor: incident ? toneVars.danger.line : 'var(--line)',
                    color: 'var(--fg-muted)',
                  }}
                >
                  {turn.text}
                </div>
                <div
                  className={cn(
                    'mt-1 flex items-center gap-1.5 text-[10.5px] text-[var(--fg-subtle)]',
                    isAgent ? '' : 'justify-end',
                  )}
                >
                  <span className="mono">#{turn.i}</span>
                  <span>{isAgent ? 'Sunil' : 'Caller'}</span>
                  {turn.language && (
                    <span
                      className="rounded-[4px] border px-1 py-px"
                      style={{ borderColor: 'var(--line-strong)' }}
                    >
                      {languageName(turn.language)}
                    </span>
                  )}
                  {turn.flags?.includes('code_switch') && (
                    <span className="text-[var(--violet)]">code-switch</span>
                  )}
                  {incident && (
                    <span className="inline-flex items-center gap-1 font-medium text-[var(--danger)]">
                      <TriangleAlert size={10} />
                      {titleize(incident.category)} · {incident.detector}
                    </span>
                  )}
                </div>
              </div>
            </motion.div>
          )
        })}

        {call.transcript.length === 0 && (
          <EmptyState
            icon={<MessageSquare size={17} />}
            title="Listening…"
            hint="The transcript fills in turn by turn while the call is live."
          />
        )}
      </div>
    </div>
  )
}

export function TranscriptDrawer({
  open,
  onOpenChange,
  call,
}: {
  open: boolean
  onOpenChange: (v: boolean) => void
  call?: CallRecord
}) {
  return (
    <Drawer
      open={open}
      onOpenChange={onOpenChange}
      title="Call transcript"
      description={
        call
          ? `${call.from_number ?? 'Unknown'} · ${languageName(call.language_detected)} · ${
              call.transcript.length
            } turns`
          : undefined
      }
      width={620}
    >
      <TranscriptBody call={call} />
    </Drawer>
  )
}
