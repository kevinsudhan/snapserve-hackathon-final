import { Link, useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { toast } from 'sonner'
import {
  Activity,
  BookOpenCheck,
  Copy,
  FileSearch,
  PhoneCall,
  Radio,
  ShieldCheck,
  Sparkles,
  Ticket as TicketIcon,
  TrendingUp,
} from 'lucide-react'
import type { EventType, LiveEvent } from '@/types'
import { useStats } from '@/lib/api'
import { DEMO_PHONE, ago, copyText } from '@/lib/utils'
import { useLive } from '@/store/live'
import {
  Badge,
  Button,
  EmptyState,
  LiveDot,
  Panel,
  PanelHeader,
  Skeleton,
  toneVars,
  type Tone,
} from '@/components/ui/base'
import { CountUp } from '@/components/ui/CountUp'
import { Tooltip } from '@/components/ui/overlays'
import { CallsPerHour, LanguagesRing, VerdictDonut } from '@/components/charts/StatCharts'

export default function Overview() {
  const { data: stats, isLoading } = useStats()
  const events = useLive((s) => s.events)

  return (
    <div className="space-y-4">
      {/* KPI row */}
      <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">
        {isLoading || !stats ? (
          Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-[112px] rounded-[13px]" />)
        ) : (
          <>
            <StatTile
              icon={<PhoneCall size={14} />}
              tone="sky"
              label="Calls handled"
              value={stats.calls_total}
              hint={`${stats.last_24h.reduce((n, h) => n + h.calls, 0)} in the last 24 h`}
              delay={0}
            />
            <StatTile
              icon={<FileSearch size={14} />}
              tone="accent"
              label="Claims recorded"
              value={stats.claims_total}
              hint={`${stats.verdicts.supported ?? 0} weather-supported`}
              delay={0.06}
            />
            <StatTile
              icon={<TicketIcon size={14} />}
              tone={stats.tickets_open > 0 ? 'warn' : 'ok'}
              label="Open tickets"
              value={stats.tickets_open}
              hint="Escalations waiting on a person"
              delay={0.12}
            />
            <GuardrailTile incidents={stats.guardrail_incidents} />
          </>
        )}
      </div>

      {/* charts */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Panel>
          <PanelHeader
            eyebrow="Truth check"
            title="Verdict distribution"
            icon={<ShieldCheck size={14} />}
            tone="accent"
          />
          <div className="px-5 pt-1 pb-5">
            {stats ? <VerdictDonut verdicts={stats.verdicts} /> : <Skeleton className="h-[152px]" />}
          </div>
        </Panel>

        <Panel>
          <PanelHeader
            eyebrow="Last 24 hours"
            title="Calls per hour"
            icon={<TrendingUp size={14} />}
            tone="sky"
          />
          <div className="px-3 pb-4">
            {stats ? <CallsPerHour series={stats.last_24h} /> : <Skeleton className="mx-2 h-[188px]" />}
          </div>
        </Panel>

        <Panel>
          <PanelHeader
            eyebrow="Any language"
            title="Languages detected"
            icon={<Sparkles size={14} />}
            tone="violet"
          />
          <div className="px-5 pt-1 pb-5">
            {stats ? <LanguagesRing languages={stats.languages} /> : <Skeleton className="h-[152px]" />}
          </div>
        </Panel>
      </div>

      {/* feed + judge actions */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Panel className="lg:col-span-2">
          <PanelHeader
            eyebrow="WebSocket"
            title="Live activity"
            icon={<Activity size={14} />}
            tone="accent"
            right={<LiveDot />}
          />
          <ActivityFeed events={events} />
        </Panel>

        <JudgeActions />
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ */

function StatTile({
  icon,
  label,
  value,
  hint,
  tone,
  delay = 0,
}: {
  icon: React.ReactNode
  label: string
  value: number
  hint: string
  tone: Tone
  delay?: number
}) {
  const t = toneVars[tone]
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.32, delay, ease: [0.22, 1, 0.36, 1] }}
    >
      <Panel className="relative overflow-hidden px-5 py-4">
        <span
          className="pointer-events-none absolute -top-8 -right-8 size-28 rounded-full opacity-40 blur-2xl"
          style={{ background: t.bg }}
          aria-hidden
        />
        <div className="mb-3 flex items-center gap-2">
          <span
            className="grid size-6 place-items-center rounded-[7px] border"
            style={{ color: t.fg, background: t.bg, borderColor: t.line }}
          >
            {icon}
          </span>
          <span className="eyebrow">{label}</span>
        </div>
        <div className="display text-[32px] leading-none">
          <CountUp value={value} />
        </div>
        <div className="mt-2 truncate text-[11.5px] text-[var(--fg-subtle)]">{hint}</div>
      </Panel>
    </motion.div>
  )
}

function GuardrailTile({ incidents }: { incidents: number }) {
  const clean = incidents === 0
  const t = toneVars[clean ? 'ok' : 'danger']
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.32, delay: 0.18, ease: [0.22, 1, 0.36, 1] }}
    >
      <Panel
        className="relative overflow-hidden px-5 py-4"
        style={clean ? { borderColor: 'var(--accent-line)' } : { borderColor: t.line }}
      >
        <span
          className="pointer-events-none absolute inset-0 opacity-70"
          style={{
            background: clean
              ? 'radial-gradient(280px 100px at 85% 0%, var(--accent-soft), transparent)'
              : 'radial-gradient(280px 100px at 85% 0%, var(--danger-soft), transparent)',
          }}
          aria-hidden
        />
        <div className="relative mb-3 flex items-center gap-2">
          <span
            className="grid size-6 place-items-center rounded-[7px] border"
            style={{ color: t.fg, background: t.bg, borderColor: t.line }}
          >
            <ShieldCheck size={14} />
          </span>
          <span className="eyebrow">Guardrail incidents</span>
        </div>
        <div className="relative flex items-end gap-2.5">
          <span className="display text-[32px] leading-none" style={{ color: clean ? 'var(--ok)' : t.fg }}>
            <CountUp value={incidents} />
          </span>
          {clean && (
            <Tooltip content="No payout, approval or timeline promise; no invented scheme fact; no missed escalation — across every call in this dataset.">
              <span className="mb-0.5">
                <Badge tone="ok" dot>
                  clean sheet
                </Badge>
              </span>
            </Tooltip>
          )}
        </div>
        <div className="relative mt-2 truncate text-[11.5px] text-[var(--fg-subtle)]">
          {clean ? 'Rules + LLM judge, every agent turn' : 'Open the guardrails page to review'}
        </div>
      </Panel>
    </motion.div>
  )
}

/* ------------------------------------------------------------------ */

const EVENT_TONE: Record<string, Tone> = {
  'call.started': 'sky',
  'call.completed': 'neutral',
  'claim.created': 'accent',
  'claim.updated': 'accent',
  'ticket.created': 'danger',
  'ticket.updated': 'warn',
  'evidence.uploaded': 'teal',
  'knowledge.refreshed': 'violet',
  'guardrail.incident': 'danger',
  'eval.progress': 'violet',
  'eval.completed': 'violet',
  'poller.status': 'neutral',
}

const EVENT_LABEL: Partial<Record<EventType, string>> = {
  'call.started': 'Call started',
  'call.completed': 'Call completed',
  'claim.created': 'Claim opened',
  'claim.updated': 'Claim updated',
  'ticket.created': 'Escalated to a person',
  'ticket.updated': 'Ticket updated',
  'evidence.uploaded': 'Evidence uploaded',
  'knowledge.refreshed': 'Knowledge refreshed',
  'guardrail.incident': 'Guardrail incident',
  'eval.progress': 'Eval progress',
  'eval.completed': 'Eval finished',
  'poller.status': 'Poller status',
}

function describe(e: LiveEvent): string {
  const p = e.payload as {
    call?: { from_number?: string }
    claim?: { reference?: string; location?: { district?: string } }
    ticket?: { reference?: string; severity?: string }
    claim_reference?: string
    step?: string
    scenario?: string
  }
  if (p.claim?.reference) return `${p.claim.reference}${p.step ? ` · ${p.step.replace(/_/g, ' ')}` : ''}`
  if (p.ticket?.reference) return `${p.ticket.reference} · ${p.ticket.severity} severity`
  if (p.call?.from_number) return p.call.from_number
  if (p.claim_reference) return p.claim_reference
  if (p.scenario) return p.scenario
  return ''
}

function ActivityFeed({ events }: { events: LiveEvent[] }) {
  if (events.length === 0) {
    return (
      <EmptyState
        icon={<Activity size={17} />}
        title="Waiting for the first event"
        hint="Every call, claim, ticket and upload lands here the moment the backend emits it."
      />
    )
  }
  return (
    <ul className="max-h-[330px] overflow-y-auto px-5 pb-4">
      {events.slice(0, 20).map((e, i) => {
        const tone = EVENT_TONE[e.type] ?? 'neutral'
        const t = toneVars[tone]
        return (
          <motion.li
            key={`${e.at}-${e.type}-${i}`}
            initial={{ opacity: 0, x: -8 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.24 }}
            className="relative flex items-center gap-3 py-2.5 pl-4"
            style={{ borderTop: i === 0 ? 'none' : '1px solid var(--line)' }}
          >
            <span
              className="absolute top-0 bottom-0 left-[3px] w-px"
              style={{ background: 'var(--line)' }}
              aria-hidden
            />
            <span
              className="absolute left-0 size-[7px] rounded-full border-2"
              style={{ background: t.fg, borderColor: 'var(--bg)' }}
              aria-hidden
            />
            <span className="text-[12.5px] font-medium">{EVENT_LABEL[e.type] ?? e.type}</span>
            <span className="mono min-w-0 flex-1 truncate text-[11.5px] text-[var(--fg-subtle)]">
              {describe(e)}
            </span>
            <span className="mono shrink-0 text-[11px] text-[var(--fg-subtle)]">{ago(e.at)}</span>
          </motion.li>
        )
      })}
    </ul>
  )
}

/* ------------------------------------------------------------------ */

function JudgeActions() {
  const navigate = useNavigate()
  return (
    <Panel className="relative overflow-hidden">
      <span
        className="pointer-events-none absolute inset-0"
        style={{ background: 'radial-gradient(420px 160px at 100% 0%, var(--accent-soft), transparent)' }}
        aria-hidden
      />
      <PanelHeader
        eyebrow="For the demo"
        title="Judge quick actions"
        icon={<Sparkles size={14} />}
        tone="accent"
      />
      <div className="relative space-y-2.5 px-5 pb-5">
        <button
          onClick={async () => {
            await copyText(DEMO_PHONE)
            toast.success('Number copied', { description: `Call ${DEMO_PHONE} to talk to Sunil.` })
          }}
          className="flex w-full items-center gap-3 rounded-[11px] border px-3.5 py-3 text-left transition-colors duration-150 hover:border-[var(--accent-line)]"
          style={{ background: 'var(--surface-inset)', borderColor: 'var(--line)' }}
        >
          <span
            className="grid size-8 shrink-0 place-items-center rounded-[9px] border"
            style={{ background: 'var(--accent-soft)', borderColor: 'var(--accent-line)', color: 'var(--accent-fg)' }}
          >
            <PhoneCall size={15} />
          </span>
          <span className="min-w-0 flex-1">
            <span className="block text-[13px] font-semibold">Call the agent</span>
            <span className="mono block text-[12px] text-[var(--fg-subtle)]">{DEMO_PHONE}</span>
          </span>
          <Copy size={14} className="shrink-0 text-[var(--fg-subtle)]" />
        </button>

        <Button
          variant="subtle"
          size="md"
          className="w-full justify-start"
          icon={<Radio size={14} />}
          onClick={() => navigate('/live')}
        >
          Open the Live Desk
          <span className="ml-auto text-[11px] text-[var(--fg-subtle)]">watch a call land</span>
        </Button>

        <Button
          variant="subtle"
          size="md"
          className="w-full justify-start"
          icon={<BookOpenCheck size={14} />}
          onClick={() => navigate('/knowledge')}
        >
          Open the Knowledge snapshot
          <span className="ml-auto text-[11px] text-[var(--fg-subtle)]">map + sources</span>
        </Button>

        <p className="pt-1 text-[11.5px] leading-relaxed text-[var(--fg-subtle)]">
          The agent makes no tool calls at runtime — everything it may say is baked into the prompt from
          the snapshot, and{' '}
          <Link to="/claims" className="text-[var(--accent-fg)] hover:underline">
            every claim
          </Link>{' '}
          re-checks that against the same real data.
        </p>
      </div>
    </Panel>
  )
}
