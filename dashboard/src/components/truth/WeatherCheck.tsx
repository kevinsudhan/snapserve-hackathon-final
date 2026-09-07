import { useMemo } from 'react'
import { motion } from 'framer-motion'
import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip as RTooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { CalendarClock, CloudRain, ExternalLink, Wind } from 'lucide-react'
import type { Claim, WeatherEvidence } from '@/types'
import { VERDICT_BLURB, VERDICT_LABEL, VERDICT_TONE } from '@/lib/tone'
import { fmtDate, fmtDateTime, kmh, mm, nf, shortDay, titleize } from '@/lib/utils'
import { Badge, Panel, PanelHeader, toneVars } from '@/components/ui/base'
import { Tooltip } from '@/components/ui/overlays'
import { CitationChip } from './CitationChip'

const RAIN_GUIDE = 50 // mm/day — PMFBY heavy-rain threshold used by check_weather
const GUST_GUIDE = 60 // km/h — cyclone gust threshold used by check_weather

export function WeatherCheck({ claim }: { claim: Claim }) {
  const w = claim.weather_evidence
  const tone = VERDICT_TONE[w.verdict]
  const t = toneVars[tone]

  const data = useMemo(
    () =>
      w.daily.map((d) => ({
        date: d.date,
        label: shortDay(d.date),
        rain: d.precipitation_mm,
        gust: d.wind_gust_kmh,
        temp: d.temp_max_c,
      })),
    [w.daily],
  )

  const eventIdx = data.findIndex((d) => d.date === claim.event_date)
  const windowStart = data[Math.max(0, eventIdx - 1)]?.label
  const windowEnd = data[Math.min(data.length - 1, eventIdx + 1)]?.label

  if (!w.daily.length) {
    if (w.verdict === 'unverifiable' || w.source === 'none') return <WeatherUnverifiable claim={claim} />
    return <WeatherPending />
  }

  return (
    <Panel>
      <PanelHeader
        eyebrow="Step 2 · weather truth-check"
        title={`${titleize(claim.damage_type)} on ${fmtDate(claim.event_date)}`}
        icon={<CloudRain size={14} />}
        tone="sky"
        right={
          <Tooltip content={VERDICT_BLURB[w.verdict]}>
            <motion.span
              initial={{ opacity: 0, scale: 0.94 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
              className="inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-[12.5px] font-semibold"
              style={{ color: t.fg, background: t.bg, borderColor: t.line }}
            >
              <span className="size-1.5 rounded-full" style={{ background: t.fg }} />
              {VERDICT_LABEL[w.verdict]}
            </motion.span>
          </Tooltip>
        }
      />

      <div className="px-5 pb-2">
        <p className="text-[13px] leading-relaxed text-[var(--fg-muted)]">
          <span className="text-[var(--fg-subtle)]">Said to the farmer — </span>
          <span className="text-[var(--fg)]">“{w.farmer_sentence}”</span>
        </p>
      </div>

      {/* legend */}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 px-5 pt-2 pb-1 text-[11px] text-[var(--fg-subtle)]">
        <LegendItem swatch={<span className="h-2.5 w-2 rounded-[2px]" style={{ background: 'var(--sky)' }} />}>
          Daily rain (mm)
        </LegendItem>
        <LegendItem
          swatch={<span className="h-0.5 w-4 rounded-full" style={{ background: 'var(--violet)' }} />}
        >
          Max wind gust (km/h)
        </LegendItem>
        <LegendItem
          swatch={
            <span
              className="h-2.5 w-3 rounded-[2px] border"
              style={{ background: t.bg, borderColor: t.line }}
            />
          }
        >
          Claimed event window
        </LegendItem>
        <LegendItem
          swatch={
            <span
              className="h-0 w-4 border-t border-dashed"
              style={{ borderColor: 'var(--fg-subtle)' }}
            />
          }
        >
          Thresholds ({RAIN_GUIDE} mm · {GUST_GUIDE} km/h)
        </LegendItem>
      </div>

      <div className="h-[248px] px-2 pb-1">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data} margin={{ top: 12, right: 14, bottom: 4, left: 4 }}>
            <defs>
              <linearGradient id="rainGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="var(--sky)" stopOpacity={0.95} />
                <stop offset="100%" stopColor="var(--sky)" stopOpacity={0.28} />
              </linearGradient>
            </defs>

            <CartesianGrid vertical={false} stroke="var(--chart-grid)" strokeDasharray="0" />

            {eventIdx >= 0 && windowStart && windowEnd && (
              <ReferenceArea
                x1={windowStart}
                x2={windowEnd}
                fill={t.fg}
                fillOpacity={0.1}
                stroke={t.fg}
                strokeOpacity={0.35}
                strokeDasharray="3 3"
              />
            )}

            <XAxis
              dataKey="label"
              tick={{ fontSize: 10, fill: 'var(--fg-subtle)', fontFamily: 'var(--font-mono)' }}
              tickLine={false}
              axisLine={{ stroke: 'var(--line)' }}
              interval={Math.max(1, Math.floor(data.length / 9))}
              tickMargin={8}
            />
            <YAxis
              yAxisId="rain"
              tick={{ fontSize: 10, fill: 'var(--fg-subtle)', fontFamily: 'var(--font-mono)' }}
              tickLine={false}
              axisLine={false}
              width={34}
            />
            <YAxis
              yAxisId="gust"
              orientation="right"
              tick={{ fontSize: 10, fill: 'var(--fg-subtle)', fontFamily: 'var(--font-mono)' }}
              tickLine={false}
              axisLine={false}
              width={34}
            />

            <ReferenceLine
              yAxisId="rain"
              y={RAIN_GUIDE}
              stroke="var(--fg-subtle)"
              strokeDasharray="4 4"
              strokeOpacity={0.55}
            />
            <ReferenceLine
              yAxisId="gust"
              y={GUST_GUIDE}
              stroke="var(--violet)"
              strokeDasharray="4 4"
              strokeOpacity={0.45}
            />

            <RTooltip cursor={{ fill: 'var(--surface-3)', opacity: 0.5 }} content={<ChartTooltip />} />

            <Bar
              yAxisId="rain"
              dataKey="rain"
              fill="url(#rainGrad)"
              radius={[3, 3, 0, 0]}
              maxBarSize={16}
              isAnimationActive
              animationDuration={620}
            />
            <Line
              yAxisId="gust"
              type="monotone"
              dataKey="gust"
              stroke="var(--violet)"
              strokeWidth={1.75}
              dot={false}
              activeDot={{ r: 3.5, strokeWidth: 0 }}
              isAnimationActive
              animationDuration={720}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      {/* metrics */}
      <div className="grid grid-cols-2 gap-px px-0 md:grid-cols-4" style={{ background: 'var(--line)' }}>
        {Object.entries(w.metrics)
          .slice(0, 8)
          .map(([k, v]) => (
            <div key={k} className="px-5 py-2.5" style={{ background: 'var(--surface-1)' }}>
              <div className="eyebrow truncate">{metricLabel(k)}</div>
              <div className="mono mt-0.5 text-[14px] font-semibold">
                {k.includes('mm') ? mm(v) : k.includes('kmh') ? kmh(v) : nf(v, v % 1 ? 2 : 0)}
              </div>
            </div>
          ))}
      </div>

      {/* reasons */}
      <div className="space-y-2 px-5 pt-4">
        <div className="eyebrow">Why this verdict</div>
        <ul className="space-y-1.5">
          {w.reasons.map((r, i) => (
            <motion.li
              key={r}
              initial={{ opacity: 0, x: -6 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.25, delay: i * 0.06 }}
              className="flex gap-2.5 text-[12.5px] leading-relaxed text-[var(--fg-muted)]"
            >
              <span
                className="mt-[7px] size-1 shrink-0 rounded-full"
                style={{ background: t.fg }}
                aria-hidden
              />
              {r}
            </motion.li>
          ))}
        </ul>
      </div>

      {w.nearby_matching_dates.length > 0 && (
        <div className="mt-4 mx-5 rounded-[10px] border p-3" style={{ background: 'var(--warn-soft)', borderColor: toneVars.warn.line }}>
          <div className="mb-2 flex items-center gap-1.5 text-[12px] font-semibold" style={{ color: 'var(--warn)' }}>
            <CalendarClock size={13} />
            Nearby dates that would match
          </div>
          <p className="mb-2 text-[11.5px] text-[var(--fg-muted)]">
            Offered to the farmer as a gentle probe — a misremembered date is far more common than a
            false claim.
          </p>
          <div className="flex flex-wrap gap-1.5">
            {w.nearby_matching_dates.map((d) => (
              <span
                key={d}
                className="mono rounded-full border px-2 py-[3px] text-[11px]"
                style={{ borderColor: toneVars.warn.line, color: 'var(--warn)' }}
              >
                {fmtDate(d)}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* provenance */}
      <div className="mt-4 flex flex-wrap items-center gap-x-3 gap-y-2 px-5 pt-3 pb-4" style={{ borderTop: '1px solid var(--line)' }}>
        <Badge tone={w.source === 'snapshot' ? 'sky' : 'warn'}>
          source: {w.source === 'snapshot' ? '60-day snapshot' : 'unavailable'}
        </Badge>
        <span className="text-[11px] text-[var(--fg-subtle)]">
          window {fmtDate(w.window.start)} → {fmtDate(w.window.end)} · pulled {fmtDateTime(w.fetched_at)}
        </span>
        <div className="ml-auto flex items-center gap-1.5">
          {w.citations.map((c) => (
            <CitationChip key={c.id} citation={c} compact />
          ))}
          {w.request_url && (
            <a
              href={w.request_url}
              target="_blank"
              rel="noreferrer noopener"
              className="inline-flex items-center gap-1 text-[11px] text-[var(--fg-subtle)] hover:text-[var(--fg)]"
            >
              request <ExternalLink size={10} />
            </a>
          )}
        </div>
      </div>
    </Panel>
  )
}

/** `max_2day_rain_mm` → "max 2day rain" — the unit is already in the value */
function metricLabel(key: string) {
  return key
    .replace(/_(mm|kmh|c|km|ratio)$/, '')
    .replace(/_/g, ' ')
}

function LegendItem({ swatch, children }: { swatch: React.ReactNode; children: React.ReactNode }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      {swatch}
      {children}
    </span>
  )
}

type TooltipPayload = { payload: { date: string; rain: number; gust: number; temp: number } }

function ChartTooltip({ active, payload }: { active?: boolean; payload?: TooltipPayload[] }) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload
  return (
    <div
      className="rounded-[9px] border px-3 py-2 text-[11.5px]"
      style={{
        background: 'var(--surface-3)',
        borderColor: 'var(--line-strong)',
        boxShadow: 'var(--pop-shadow)',
      }}
    >
      <div className="mono mb-1.5 text-[11px] font-semibold">{fmtDate(d.date)}</div>
      <Row icon={<CloudRain size={11} />} color="var(--sky)" label="Rain" value={mm(d.rain)} />
      <Row icon={<Wind size={11} />} color="var(--violet)" label="Gust" value={kmh(d.gust)} />
      <Row label="Max temp" value={`${nf(d.temp, 1)} °C`} color="var(--fg-subtle)" />
    </div>
  )
}

function Row({
  icon,
  label,
  value,
  color,
}: {
  icon?: React.ReactNode
  label: string
  value: string
  color: string
}) {
  return (
    <div className="flex items-center gap-2 py-px">
      <span style={{ color }} className="flex w-3 justify-center">
        {icon}
      </span>
      <span className="text-[var(--fg-subtle)]">{label}</span>
      <span className="mono ml-auto font-medium">{value}</span>
    </div>
  )
}

function WeatherPending() {
  return (
    <Panel className="flex h-[220px] flex-col items-center justify-center gap-3">
      <div
        className="grid size-9 place-items-center rounded-[10px] border"
        style={{ background: 'var(--sky-soft)', borderColor: toneVars.sky.line, color: 'var(--sky)' }}
      >
        <CloudRain size={16} />
      </div>
      <div className="text-center">
        <div className="text-[13px] font-semibold">Checking the weather record…</div>
        <div className="mt-1 text-[11.5px] text-[var(--fg-subtle)]">
          Reading the 60-day snapshot for the resolved district centroid.
        </div>
      </div>
      <div className="mt-1 h-1 w-40 overflow-hidden rounded-full" style={{ background: 'var(--surface-inset)' }}>
        <span
          className="block h-full w-1/3 rounded-full"
          style={{ background: 'var(--sky)', animation: 'sweep 1.4s ease-in-out infinite' }}
        />
      </div>
    </Panel>
  )
}

export type { WeatherEvidence }

function WeatherUnverifiable({ claim }: { claim: Claim }) {
  const w = claim.weather_evidence
  return (
    <Panel className="flex min-h-[220px] flex-col items-center justify-center gap-3 px-6 text-center">
      <div
        className="grid size-9 place-items-center rounded-[10px] border"
        style={{ background: 'var(--surface-inset)', borderColor: 'var(--line-strong)', color: 'var(--fg-subtle)' }}
      >
        <CloudRain size={16} />
      </div>
      <div>
        <div className="text-[13px] font-semibold">Weather could not be verified</div>
        <div className="mt-1 max-w-[420px] text-[11.5px] text-[var(--fg-subtle)]">
          {w.reasons[0] ?? 'The place or date needed for the check was not captured on the call.'}
        </div>
      </div>
      <div className="mono text-[10.5px] text-[var(--fg-subtle)]">verdict · unverifiable — escalated to a reviewer, never treated as verified</div>
    </Panel>
  )
}
