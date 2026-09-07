import { motion } from 'framer-motion'
import {
  AlertOctagon,
  ArrowUpRight,
  CalendarRange,
  CircleHelp,
  MessageSquareQuote,
  Scale,
  Waves,
} from 'lucide-react'
import type { Claim } from '@/types'
import { alertTone } from '@/lib/tone'
import { fmtDate, titleize } from '@/lib/utils'
import { Badge, EmptyState, Panel, PanelHeader, toneVars } from '@/components/ui/base'
import { CitationChip } from './CitationChip'

/* ------------------------------------------------------------------ *
 * Disaster events (GDACS, from the snapshot)
 * ------------------------------------------------------------------ */

export function DisasterCards({ claim }: { claim: Claim }) {
  const d = claim.disaster_evidence
  return (
    <Panel>
      <PanelHeader
        eyebrow="Step 3"
        title="Disaster events near the field"
        icon={<Waves size={14} />}
        tone="violet"
        right={
          d.events.length > 0 ? (
            <Badge tone="violet">{d.events.length} in window</Badge>
          ) : (
            <Badge tone="neutral">none</Badge>
          )
        }
      />
      {d.events.length === 0 ? (
        <EmptyState
          icon={<Waves size={17} />}
          tone="violet"
          title="No GDACS event within 300 km"
          hint="Absence of an alert is not evidence against the claim — it only means no global alert was raised in that window."
          className="py-9"
        />
      ) : (
        <div className="grid gap-2.5 px-5 pb-5 md:grid-cols-2">
          {d.events.map((e, i) => {
            const tone = alertTone(e.alert_level)
            const t = toneVars[tone]
            return (
              <motion.a
                key={e.id}
                href={e.report_url}
                target="_blank"
                rel="noreferrer noopener"
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.26, delay: i * 0.06 }}
                className="group relative overflow-hidden rounded-[11px] border p-3.5 transition-colors duration-150 hover:border-[var(--line-strong)]"
                style={{ background: 'var(--surface-inset)', borderColor: 'var(--line)' }}
              >
                <span
                  className="absolute inset-y-0 left-0 w-[3px]"
                  style={{ background: t.fg }}
                  aria-hidden
                />
                <div className="mb-2 flex items-center gap-2">
                  <Badge tone={tone} dot>
                    {e.alert_level} · {e.type}
                  </Badge>
                  <span className="mono text-[10.5px] text-[var(--fg-subtle)]">{e.id}</span>
                  <ArrowUpRight
                    size={13}
                    className="ml-auto text-[var(--fg-subtle)] transition-transform duration-150 group-hover:-translate-y-0.5 group-hover:translate-x-0.5"
                  />
                </div>
                <div className="text-[13px] leading-snug font-semibold">{e.name}</div>
                <div className="mono mt-1.5 text-[11px] text-[var(--fg-subtle)]">
                  {fmtDate(e.from)} → {fmtDate(e.to)}
                  {e.distance_km != null && ` · ${e.distance_km} km away`}
                </div>
              </motion.a>
            )
          })}
        </div>
      )}
      {d.citations.length > 0 && (
        <div
          className="flex items-center gap-2 px-5 py-2.5 text-[11px] text-[var(--fg-subtle)]"
          style={{ borderTop: '1px solid var(--line)' }}
        >
          GDACS feed read from the snapshot
          <span className="ml-auto flex gap-1.5">
            {d.citations.map((c) => (
              <CitationChip key={c.id} citation={c} compact />
            ))}
          </span>
        </div>
      )}
    </Panel>
  )
}

/* ------------------------------------------------------------------ *
 * Crop window
 * ------------------------------------------------------------------ */

export function CropWindow({ claim }: { claim: Claim }) {
  const c = claim.crop_evidence
  if (!c) return null
  const tone = c.in_window === true ? 'ok' : c.in_window === false ? 'danger' : 'neutral'
  const label =
    c.in_window === true ? 'Inside the window' : c.in_window === false ? 'Outside the window' : 'Not applicable'

  return (
    <Panel>
      <PanelHeader
        eyebrow="Step 4"
        title="Crop calendar check"
        icon={<CalendarRange size={14} />}
        tone="accent"
        right={<Badge tone={tone} dot>{label}</Badge>}
      />
      <div className="space-y-3 px-5 pb-5">
        <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
          <Cell label="Crop" value={titleize(c.crop)} />
          <Cell label="District" value={c.district ?? '—'} />
          <Cell label="Season" value={c.season ?? '—'} />
          <Cell label="Sowing → harvest" value={c.window ? `${c.window.sowing} → ${c.window.harvest}` : '—'} />
        </div>
        <p className="text-[12.5px] leading-relaxed text-[var(--fg-muted)]">{c.note}</p>
        {c.citations.length > 0 && (
          <div className="flex items-center gap-1.5">
            {c.citations.map((cit) => (
              <CitationChip key={cit.id} citation={cit} />
            ))}
          </div>
        )}
      </div>
    </Panel>
  )
}

function Cell({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <div className="eyebrow mb-1">{label}</div>
      <div className="text-[13px] leading-snug font-medium">{value}</div>
    </div>
  )
}

/* ------------------------------------------------------------------ *
 * Scheme facts + unknowns
 * ------------------------------------------------------------------ */

export function SchemeFacts({ claim }: { claim: Claim }) {
  const said = new Set(claim.agent_said_facts.filter((f) => f.verified).map((f) => f.fact_id))
  return (
    <Panel>
      <PanelHeader
        eyebrow="Step 5"
        title="Scheme facts the agent could rely on"
        icon={<Scale size={14} />}
        tone="teal"
        right={<Badge tone="teal">{claim.scheme_matches.length} facts</Badge>}
      />

      {claim.scheme_matches.length === 0 ? (
        <EmptyState
          icon={<Scale size={17} />}
          tone="teal"
          title="Matching scheme facts not loaded yet"
          hint="lookup_scheme runs once the crop, district and damage type are all confirmed."
          className="py-9"
        />
      ) : (
        <ul className="px-5 pb-1">
          {claim.scheme_matches.map((m, i) => (
            <motion.li
              key={m.fact_id}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.24, delay: i * 0.05 }}
              className="flex items-start gap-3 py-3"
              style={{ borderBottom: '1px solid var(--line)' }}
            >
              <div className="min-w-0 flex-1">
                <div className="mb-1 flex flex-wrap items-center gap-2">
                  <span className="text-[11.5px] font-semibold text-[var(--teal)]">{m.scheme}</span>
                  <span className="mono text-[10.5px] text-[var(--fg-subtle)]">
                    {m.field.replace(/_/g, ' ')}
                  </span>
                  {said.has(m.fact_id) && (
                    <Badge tone="ok">
                      <MessageSquareQuote size={10} />
                      quoted on the call
                    </Badge>
                  )}
                </div>
                <p className="text-[12.5px] leading-relaxed text-[var(--fg-muted)]">{m.text}</p>
              </div>
              <CitationChip citation={m.citation} />
            </motion.li>
          ))}
        </ul>
      )}

      {claim.unknowns.length > 0 && (
        <div className="m-5 mt-4 rounded-[11px] border p-3.5" style={{ background: 'var(--surface-inset)', borderColor: 'var(--line)' }}>
          <div className="mb-2 flex items-center gap-1.5 text-[12px] font-semibold text-[var(--fg-muted)]">
            <CircleHelp size={13} />
            Stated as unknown — the agent must not guess these
          </div>
          <ul className="space-y-1.5">
            {claim.unknowns.map((u) => (
              <li key={u} className="flex gap-2.5 text-[12px] leading-relaxed text-[var(--fg-subtle)]">
                <span className="mt-[7px] size-1 shrink-0 rounded-full bg-[var(--fg-subtle)]" aria-hidden />
                {u}
              </li>
            ))}
          </ul>
        </div>
      )}
    </Panel>
  )
}

/* ------------------------------------------------------------------ *
 * Escalation
 * ------------------------------------------------------------------ */

export function EscalationCard({ claim }: { claim: Claim }) {
  if (!claim.escalation_reason && !claim.farmer_explanation) return null
  return (
    <Panel
      className="relative overflow-hidden"
      style={{ borderColor: toneVars.danger.line }}
    >
      <span
        className="pointer-events-none absolute inset-x-0 top-0 h-24 opacity-60"
        style={{ background: 'radial-gradient(420px 90px at 20% 0%, var(--danger-soft), transparent)' }}
        aria-hidden
      />
      <PanelHeader
        eyebrow="Escalated"
        title="Handed to a person"
        icon={<AlertOctagon size={14} />}
        tone="danger"
      />
      <div className="grid gap-3 px-5 pb-5 md:grid-cols-2">
        <div className="rounded-[11px] border p-3.5" style={{ background: 'var(--surface-inset)', borderColor: 'var(--line)' }}>
          <div className="eyebrow mb-1.5">Why (full detail, for the reviewer)</div>
          <p className="text-[12.5px] leading-relaxed text-[var(--fg-muted)]">{claim.escalation_reason}</p>
        </div>
        <div
          className="rounded-[11px] border p-3.5"
          style={{ background: 'var(--accent-soft)', borderColor: 'var(--accent-line)' }}
        >
          <div className="eyebrow mb-1.5" style={{ color: 'var(--accent-fg)' }}>
            What we told the farmer
          </div>
          <p className="text-[12.5px] leading-relaxed text-[var(--fg)]">
            “{claim.farmer_explanation}”
          </p>
          <p className="mt-2 text-[11px] text-[var(--fg-subtle)]">
            Non-accusatory, in the caller’s language, and never a rejection.
          </p>
        </div>
      </div>
    </Panel>
  )
}
