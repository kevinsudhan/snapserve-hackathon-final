import { useMemo } from 'react'
import {
  Bar,
  BarChart,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip as RTooltip,
  XAxis,
} from 'recharts'
import type { Stats, Verdict } from '@/types'
import { VERDICT_LABEL, VERDICT_TONE } from '@/lib/tone'
import { languageName, nf } from '@/lib/utils'
import { toneVars } from '@/components/ui/base'
import { CountUp } from '@/components/ui/CountUp'

const format = (h: string) => new Date(h).getHours().toString().padStart(2, '0')

/* ------------------------------------------------------------------ *
 * Verdict distribution — donut
 * ------------------------------------------------------------------ */

export function VerdictDonut({ verdicts }: { verdicts: Stats['verdicts'] }) {
  const data = useMemo(
    () =>
      (Object.keys(VERDICT_LABEL) as Verdict[])
        .map((k) => ({
          key: k,
          name: VERDICT_LABEL[k],
          value: verdicts[k] ?? 0,
          color: toneVars[VERDICT_TONE[k]].fg,
        }))
        .filter((d) => d.value > 0),
    [verdicts],
  )
  const total = data.reduce((n, d) => n + d.value, 0)

  if (total === 0) {
    return (
      <div className="flex h-[188px] items-center justify-center text-[12.5px] text-[var(--fg-subtle)]">
        No verdicts yet.
      </div>
    )
  }

  return (
    <div className="flex items-center gap-4">
      <div className="relative size-[152px] shrink-0">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={data}
              dataKey="value"
              innerRadius={49}
              outerRadius={70}
              paddingAngle={3}
              cornerRadius={4}
              stroke="none"
              startAngle={90}
              endAngle={-270}
              animationDuration={720}
            >
              {data.map((d) => (
                <Cell key={d.key} fill={d.color} />
              ))}
            </Pie>
            <RTooltip content={<DonutTooltip total={total} />} />
          </PieChart>
        </ResponsiveContainer>
        <div className="pointer-events-none absolute inset-0 grid place-items-center">
          <div className="text-center">
            <div className="display text-[26px] leading-none">
              <CountUp value={total} />
            </div>
            <div className="eyebrow mt-1">claims</div>
          </div>
        </div>
      </div>

      <ul className="min-w-0 flex-1 space-y-1.5">
        {data.map((d) => (
          <li key={d.key} className="flex items-center gap-2.5">
            <span className="size-2 shrink-0 rounded-[3px]" style={{ background: d.color }} />
            <span className="min-w-0 flex-1 truncate text-[12.5px] text-[var(--fg-muted)]">{d.name}</span>
            <span className="mono text-[12.5px] font-medium">{d.value}</span>
            <span className="mono w-9 text-right text-[11px] text-[var(--fg-subtle)]">
              {Math.round((d.value / total) * 100)}%
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}

function DonutTooltip({
  active,
  payload,
  total,
}: {
  active?: boolean
  payload?: { payload: { name: string; value: number; color: string } }[]
  total: number
}) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload
  return (
    <div
      className="rounded-[9px] border px-2.5 py-1.5 text-[11.5px]"
      style={{ background: 'var(--surface-3)', borderColor: 'var(--line-strong)', boxShadow: 'var(--pop-shadow)' }}
    >
      <span className="mr-2 inline-block size-2 rounded-[3px] align-middle" style={{ background: d.color }} />
      {d.name}
      <span className="mono ml-2 font-medium">
        {d.value} · {Math.round((d.value / total) * 100)}%
      </span>
    </div>
  )
}

/* ------------------------------------------------------------------ *
 * Calls per hour — bars
 * ------------------------------------------------------------------ */

export function CallsPerHour({ series }: { series: Stats['last_24h'] }) {
  const data = useMemo(
    () => series.map((s) => ({ ...s, hour: format(s.hour) })),
    [series],
  )
  const peak = Math.max(1, ...data.map((d) => d.calls))

  return (
    <div className="h-[188px] w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 4, bottom: 0, left: 4 }} barCategoryGap="18%">
          <defs>
            <linearGradient id="callsGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--accent-hi)" stopOpacity={0.95} />
              <stop offset="100%" stopColor="var(--accent)" stopOpacity={0.3} />
            </linearGradient>
          </defs>
          <XAxis
            dataKey="hour"
            tick={{ fontSize: 10, fill: 'var(--fg-subtle)', fontFamily: 'var(--font-mono)' }}
            tickLine={false}
            axisLine={{ stroke: 'var(--line)' }}
            interval={3}
            tickMargin={7}
          />
          <RTooltip
            cursor={{ fill: 'var(--surface-3)', opacity: 0.45 }}
            content={({ active, payload, label }) =>
              active && payload?.length ? (
                <div
                  className="rounded-[9px] border px-2.5 py-1.5 text-[11.5px]"
                  style={{
                    background: 'var(--surface-3)',
                    borderColor: 'var(--line-strong)',
                    boxShadow: 'var(--pop-shadow)',
                  }}
                >
                  <span className="mono">{label}:00</span>
                  <span className="mono ml-2 font-medium">{payload[0].value} calls</span>
                </div>
              ) : null
            }
          />
          <Bar dataKey="calls" radius={[3, 3, 0, 0]} maxBarSize={16} animationDuration={680}>
            {data.map((d, i) => (
              <Cell
                key={i}
                fill={d.calls === peak ? 'var(--accent-hi)' : 'url(#callsGrad)'}
                opacity={d.calls === 0 ? 0.25 : 1}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

/* ------------------------------------------------------------------ *
 * Languages ring — concentric arcs, one per language
 * ------------------------------------------------------------------ */

const RING_COLORS = ['var(--accent-hi)', 'var(--sky)', 'var(--violet)', 'var(--teal)', 'var(--warn)', 'var(--danger)']

export function LanguagesRing({ languages }: { languages: Record<string, number> }) {
  const entries = useMemo(
    () =>
      Object.entries(languages)
        .sort((a, b) => b[1] - a[1])
        .slice(0, 6),
    [languages],
  )
  const total = entries.reduce((n, [, v]) => n + v, 0)

  if (!total) {
    return (
      <div className="flex h-[188px] items-center justify-center text-[12.5px] text-[var(--fg-subtle)]">
        No calls recorded yet.
      </div>
    )
  }

  const size = 152
  const cx = size / 2
  const cy = size / 2

  return (
    <div className="flex items-center gap-4">
      <svg width={size} height={size} className="shrink-0" role="img" aria-label="Languages detected">
        {entries.map(([code, count], i) => {
          const r = 66 - i * 11
          const c = 2 * Math.PI * r
          const frac = count / total
          return (
            <g key={code} transform={`rotate(-90 ${cx} ${cy})`}>
              <circle cx={cx} cy={cy} r={r} fill="none" stroke="var(--surface-inset)" strokeWidth={7} />
              <circle
                cx={cx}
                cy={cy}
                r={r}
                fill="none"
                stroke={RING_COLORS[i % RING_COLORS.length]}
                strokeWidth={7}
                strokeLinecap="round"
                strokeDasharray={`${c * frac} ${c}`}
                style={{
                  transition: 'stroke-dasharray 900ms cubic-bezier(0.22,1,0.36,1)',
                  filter: 'drop-shadow(0 0 6px rgba(0,0,0,0.25))',
                }}
              />
            </g>
          )
        })}
        <text
          x={cx}
          y={cy - 4}
          textAnchor="middle"
          fontSize="19"
          fontWeight="600"
          fill="var(--fg)"
          fontFamily="var(--font-sans)"
        >
          {entries.length}
        </text>
        <text
          x={cx}
          y={cy + 11}
          textAnchor="middle"
          fontSize="9"
          letterSpacing="0.09em"
          fill="var(--fg-subtle)"
          fontFamily="var(--font-sans)"
        >
          LANGUAGES
        </text>
      </svg>

      <ul className="min-w-0 flex-1 space-y-1.5">
        {entries.map(([code, count], i) => (
          <li key={code} className="flex items-center gap-2.5">
            <span
              className="size-2 shrink-0 rounded-full"
              style={{ background: RING_COLORS[i % RING_COLORS.length] }}
            />
            <span className="min-w-0 flex-1 truncate text-[12.5px] text-[var(--fg-muted)]">
              {languageName(code)}
              <span className="mono ml-1.5 text-[10.5px] text-[var(--fg-subtle)]">{code}</span>
            </span>
            <span className="mono text-[12.5px] font-medium">{nf(count)}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}
