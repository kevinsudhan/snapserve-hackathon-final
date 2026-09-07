import { motion, useReducedMotion } from 'framer-motion'
import { Gauge } from 'lucide-react'
import type { Risk } from '@/types'
import { RISK_TONE } from '@/lib/tone'
import { clamp, titleize } from '@/lib/utils'
import { Badge, EmptyState, Panel, PanelHeader, toneVars } from '@/components/ui/base'
import { CountUp } from '@/components/ui/CountUp'
import { Tooltip } from '@/components/ui/overlays'

const START = -220
const SWEEP = 260

function polar(cx: number, cy: number, r: number, deg: number) {
  const rad = (deg * Math.PI) / 180
  return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) }
}

function arcPath(cx: number, cy: number, r: number, from: number, to: number) {
  const a = polar(cx, cy, r, from)
  const b = polar(cx, cy, r, to)
  const large = Math.abs(to - from) > 180 ? 1 : 0
  return `M ${a.x} ${a.y} A ${r} ${r} 0 ${large} 1 ${b.x} ${b.y}`
}

export function RiskGauge({ risk }: { risk: Risk }) {
  const reduced = useReducedMotion()
  const tone = RISK_TONE[risk.level]
  const t = toneVars[tone]
  const score = clamp(risk.score, 0, 100)

  const size = 168
  const cx = size / 2
  const cy = size / 2
  const r = 62
  const track = arcPath(cx, cy, r, START, START + SWEEP)
  const circumference = (SWEEP / 360) * 2 * Math.PI * r

  return (
    <Panel>
      <PanelHeader
        eyebrow="Step 6"
        title="Risk score"
        icon={<Gauge size={14} />}
        tone={tone}
        right={<Badge tone={tone} dot>{titleize(risk.level)} risk</Badge>}
      />

      {risk.signals.length === 0 ? (
        <EmptyState
          icon={<Gauge size={17} />}
          title="Not scored yet"
          hint="Scoring runs after the weather, disaster and scheme checks return."
          className="py-9"
        />
      ) : (
        <div className="flex flex-col gap-5 px-5 pb-5 lg:flex-row lg:items-center">
          <div className="relative mx-auto shrink-0" style={{ width: size, height: size - 22 }}>
            <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="-mt-1">
              <path
                d={track}
                fill="none"
                stroke="var(--surface-inset)"
                strokeWidth={11}
                strokeLinecap="round"
              />
              <path
                d={track}
                fill="none"
                stroke="var(--line-strong)"
                strokeWidth={11}
                strokeLinecap="round"
                strokeDasharray="1 7"
                opacity={0.7}
              />
              <motion.path
                d={track}
                fill="none"
                stroke={t.fg}
                strokeWidth={11}
                strokeLinecap="round"
                strokeDasharray={circumference}
                initial={{ strokeDashoffset: reduced ? circumference * (1 - score / 100) : circumference }}
                animate={{ strokeDashoffset: circumference * (1 - score / 100) }}
                transition={{ duration: reduced ? 0 : 1, ease: [0.22, 1, 0.36, 1] }}
                style={{ filter: `drop-shadow(0 0 10px ${t.bg})` }}
              />
              {[0, 40, 70].map((mark) => {
                const p = polar(cx, cy, r + 12, START + (mark / 100) * SWEEP)
                return (
                  <text
                    key={mark}
                    x={p.x}
                    y={p.y}
                    textAnchor="middle"
                    dominantBaseline="middle"
                    fontSize="9"
                    fontFamily="var(--font-mono)"
                    fill="var(--fg-subtle)"
                  >
                    {mark}
                  </text>
                )
              })}
            </svg>
            <div className="absolute inset-x-0 top-[46%] -translate-y-1/2 text-center">
              <div className="display text-[38px] leading-none" style={{ color: t.fg }}>
                <CountUp value={score} />
              </div>
              <div className="eyebrow mt-1.5">of 100</div>
            </div>
          </div>

          <ul className="min-w-0 flex-1 space-y-1.5">
            {risk.signals.map((s, i) => (
              <motion.li
                key={s.code}
                initial={{ opacity: 0, x: 8 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ duration: 0.25, delay: 0.15 + i * 0.06 }}
                className="flex items-center gap-3 rounded-[9px] border px-3 py-2"
                style={{
                  background: s.weight > 0 ? 'var(--surface-inset)' : 'transparent',
                  borderColor: s.weight > 0 ? 'var(--line)' : 'transparent',
                }}
              >
                <span
                  className="size-1.5 shrink-0 rounded-full"
                  style={{ background: s.weight > 0 ? t.fg : 'var(--ok)' }}
                  aria-hidden
                />
                <div className="min-w-0 flex-1">
                  <div className="truncate text-[12.5px] text-[var(--fg-muted)]">{s.description}</div>
                  <div className="mono mt-0.5 text-[10.5px] text-[var(--fg-subtle)]">{s.code}</div>
                </div>
                <Tooltip content={s.weight > 0 ? `Adds ${s.weight} points to the risk score` : 'Neutral signal — recorded, adds nothing'}>
                  <span
                    className="mono shrink-0 rounded-[6px] border px-1.5 py-0.5 text-[11px] font-medium"
                    style={
                      s.weight > 0
                        ? { color: t.fg, background: t.bg, borderColor: t.line }
                        : { color: 'var(--ok)', background: 'var(--ok-soft)', borderColor: toneVars.ok.line }
                    }
                  >
                    {s.weight > 0 ? `+${s.weight}` : '0'}
                  </span>
                </Tooltip>
              </motion.li>
            ))}
          </ul>
        </div>
      )}
    </Panel>
  )
}
