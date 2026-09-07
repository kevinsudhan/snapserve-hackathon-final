import { useMemo } from 'react'
import { motion } from 'framer-motion'
import { toast } from 'sonner'
import { Award, CheckCircle2, Play, ShieldCheck, TriangleAlert, XCircle } from 'lucide-react'
import { useCalls, useEvalLatest, useRunEval } from '@/lib/api'
import { RISK_TONE } from '@/lib/tone'
import { ago, fmtDateTime, languageName, nf, pct, titleize } from '@/lib/utils'
import { useLive } from '@/store/live'
import { Badge, Button, EmptyState, Panel, PanelHeader, ProgressBar, Skeleton, toneVars } from '@/components/ui/base'
import { CountUp } from '@/components/ui/CountUp'

export default function Guardrails() {
  const { data: calls, isLoading } = useCalls(100)
  const { data: report } = useEvalLatest()
  const runEval = useRunEval()
  const progress = useLive((s) =>
    s.events.find((e) => e.type === 'eval.progress')?.payload as
      | { done: number; total: number; scenario: string }
      | undefined,
  )

  const incidents = useMemo(
    () =>
      (calls ?? []).flatMap((c) =>
        c.guardrail_incidents.map((i) => ({ ...i, call: c })),
      ),
    [calls],
  )

  return (
    <div className="space-y-4">
      {/* incidents */}
      <Panel className="overflow-hidden">
        <PanelHeader
          eyebrow="Post-call audit · rules + Gemini judge"
          title="Guardrail incidents"
          icon={<ShieldCheck size={14} />}
          tone={incidents.length === 0 ? 'ok' : 'danger'}
          right={
            <Badge tone={incidents.length === 0 ? 'ok' : 'danger'} dot>
              {incidents.length} across {calls?.length ?? 0} calls
            </Badge>
          }
        />

        {isLoading ? (
          <div className="space-y-1 p-4">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-[52px] rounded-[9px]" />
            ))}
          </div>
        ) : incidents.length === 0 ? (
          <TrophyEmpty calls={calls?.length ?? 0} />
        ) : (
          <ul>
            {incidents.map((inc, i) => (
              <li
                key={`${inc.call.id}-${inc.turn_index}-${i}`}
                className="grid grid-cols-[110px_150px_1fr_120px_90px] items-center gap-3 px-5 py-3"
                style={{ borderTop: '1px solid var(--line)' }}
              >
                <span className="mono truncate text-[12px]">{inc.call.snapserve_call_id}</span>
                <Badge tone="danger">{titleize(inc.category)}</Badge>
                <span className="truncate text-[12.5px] text-[var(--fg-muted)]">“{inc.text}”</span>
                <Badge tone={RISK_TONE[inc.severity]}>{titleize(inc.severity)}</Badge>
                <span className="mono text-[11px] text-[var(--fg-subtle)]">{inc.detector}</span>
              </li>
            ))}
          </ul>
        )}
      </Panel>

      {/* eval scoreboard */}
      <Panel>
        <PanelHeader
          eyebrow="Red-team harness"
          title="Eval scoreboard"
          icon={<Award size={14} />}
          tone="violet"
          right={
            <Button
              variant="primary"
              icon={<Play size={13} />}
              disabled={runEval.isPending}
              onClick={() =>
                runEval.mutate(undefined, {
                  onSuccess: () => toast('Eval run started', { description: 'Progress streams over the WebSocket.' }),
                })
              }
            >
              Run evals
            </Button>
          }
        />

        {progress && progress.done < progress.total && (
          <div className="px-5 pb-3">
            <div className="mb-1.5 flex items-center justify-between text-[11.5px] text-[var(--fg-subtle)]">
              <span className="truncate">{progress.scenario}</span>
              <span className="mono">
                {progress.done}/{progress.total}
              </span>
            </div>
            <ProgressBar value={progress.done / progress.total} tone="violet" />
          </div>
        )}

        {!report ? (
          <EmptyState
            icon={<Award size={17} />}
            tone="violet"
            title="No run yet"
            hint="The harness drives the same prompt and safe scripts in text mode across every language and bait scenario."
            action={
              <Button variant="primary" icon={<Play size={13} />} onClick={() => runEval.mutate(undefined)}>
                Run the red-team suite
              </Button>
            }
          />
        ) : (
          <>
            <div className="grid grid-cols-2 gap-px lg:grid-cols-4" style={{ background: 'var(--line)' }}>
              <Totals
                label="Pass rate"
                value={report.totals.pass_rate * 100}
                suffix="%"
                tone={report.totals.pass_rate === 1 ? 'ok' : 'warn'}
              />
              <Totals
                label="Promise leaks"
                value={report.totals.promise_leaks}
                tone={report.totals.promise_leaks === 0 ? 'ok' : 'danger'}
              />
              <Totals
                label="Fabrications"
                value={report.totals.fabrications}
                tone={report.totals.fabrications === 0 ? 'ok' : 'danger'}
              />
              <Totals
                label="Escalation failures"
                value={report.totals.escalation_failures}
                tone={report.totals.escalation_failures === 0 ? 'ok' : 'danger'}
              />
            </div>

            <div
              className="grid grid-cols-[1fr_110px_86px_86px_100px_92px] items-center gap-3 px-5 py-2.5"
              style={{ borderBottom: '1px solid var(--line)', background: 'var(--surface-inset)' }}
            >
              {['Scenario', 'Language', 'Promises', 'Fabricated', 'One question', 'Result'].map((h) => (
                <span key={h} className="eyebrow truncate">
                  {h}
                </span>
              ))}
            </div>

            <ul>
              {report.results.map((r, i) => (
                <motion.li
                  key={r.scenario}
                  initial={{ opacity: 0, y: 5 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.2, delay: Math.min(i * 0.03, 0.3) }}
                  className="grid grid-cols-[1fr_110px_86px_86px_100px_92px] items-center gap-3 px-5 py-2.5"
                  style={{ borderBottom: '1px solid var(--line)' }}
                >
                  <span className="truncate text-[12.5px]">{r.scenario}</span>
                  <span className="truncate text-[12px] text-[var(--fg-muted)]">
                    {languageName(r.language)}
                  </span>
                  <span className="mono text-[12px]">{r.promise_leaks}</span>
                  <span className="mono text-[12px]">{r.fabrications}</span>
                  <span className="mono text-[12px]">{pct(r.one_question_rate)}</span>
                  <span>
                    {r.passed ? (
                      <Badge tone="ok">
                        <CheckCircle2 size={11} />
                        pass
                      </Badge>
                    ) : (
                      <Badge tone="danger">
                        <XCircle size={11} />
                        fail
                      </Badge>
                    )}
                  </span>
                </motion.li>
              ))}
            </ul>

            <div className="px-5 py-3 text-[11px] text-[var(--fg-subtle)]">
              run <span className="mono">{report.run_id}</span> · {report.n_calls} simulated calls ·{' '}
              {report.languages.length} languages · finished {fmtDateTime(report.finished_at)} (
              {ago(report.finished_at)})
            </div>
          </>
        )}
      </Panel>
    </div>
  )
}

function Totals({
  label,
  value,
  suffix,
  tone,
}: {
  label: string
  value: number
  suffix?: string
  tone: 'ok' | 'warn' | 'danger'
}) {
  const t = toneVars[tone]
  return (
    <div className="px-5 py-4" style={{ background: 'var(--surface-1)' }}>
      <div className="eyebrow mb-1.5">{label}</div>
      <div className="display text-[26px] leading-none" style={{ color: t.fg }}>
        <CountUp value={value} decimals={suffix === '%' ? 0 : 0} suffix={suffix} />
      </div>
    </div>
  )
}

function TrophyEmpty({ calls }: { calls: number }) {
  return (
    <div className="relative overflow-hidden px-6 py-14">
      <span
        className="pointer-events-none absolute inset-0"
        style={{ background: 'radial-gradient(560px 200px at 50% 0%, var(--accent-soft), transparent)' }}
        aria-hidden
      />
      <motion.div
        initial={{ opacity: 0, scale: 0.9 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.42, ease: [0.22, 1, 0.36, 1] }}
        className="relative mx-auto flex max-w-lg flex-col items-center text-center"
      >
        <div
          className="mb-4 grid size-14 place-items-center rounded-[16px] border"
          style={{
            background: 'var(--accent-soft)',
            borderColor: 'var(--accent-line)',
            color: 'var(--accent-fg)',
            boxShadow: '0 12px 40px -18px var(--accent)',
          }}
        >
          <Award size={24} />
        </div>
        <div className="display text-[40px] leading-none" style={{ color: 'var(--ok)' }}>
          <CountUp value={0} />
        </div>
        <p className="mt-3 text-[15px] font-semibold tracking-[-0.02em]">Zero guardrail incidents</p>
        <p className="mt-2 text-[12.5px] leading-relaxed text-[var(--fg-subtle)]">
          Across {nf(calls)} audited call{calls === 1 ? '' : 's'}: no payout promise, no approval promise,
          no timeline promise, no invented scheme fact, no out-of-scope advice, no missed escalation. Every
          agent turn is checked twice — a multilingual rule list first, then a Gemini judge.
        </p>
        <div className="mt-5 flex flex-wrap justify-center gap-1.5">
          {[
            'payout_promise',
            'approval_promise',
            'timeline_promise',
            'fabricated_scheme',
            'out_of_scope_advice',
            'missed_escalation',
          ].map((c) => (
            <Badge key={c} tone="ok">
              <CheckCircle2 size={10} />
              {titleize(c)}
            </Badge>
          ))}
        </div>
        <p className="mt-5 flex items-center gap-1.5 text-[11px] text-[var(--fg-subtle)]">
          <TriangleAlert size={11} />
          If one ever fires, it lands in this table with the exact turn and the detector that caught it.
        </p>
      </motion.div>
    </div>
  )
}
