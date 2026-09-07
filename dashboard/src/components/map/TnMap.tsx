import { useMemo, useState } from 'react'
import { geoMercator, geoPath } from 'd3-geo'
import type { GeoCollection, WeatherSnapshot } from '@/types'
import { clamp, kmh, mm, nf } from '@/lib/utils'

type DistrictStat = {
  name: string
  rain7: number
  gustMax: number
  notable: string[]
}

const W = 620
const H = 720

/** normalise names so "Thoothukudi" and "Thoothukkudi" still line up */
const norm = (s: string) =>
  s
    .toLowerCase()
    .replace(/[^a-z]/g, '')
    .replace(/thiru/g, 'tiru')
    .replace(/kk/g, 'k')
    .replace(/pp/g, 'p')
    .replace(/tt/g, 't')

export function TnMap({
  geo,
  snapshot,
}: {
  geo: GeoCollection
  snapshot?: WeatherSnapshot
}) {
  const [hover, setHover] = useState<{ x: number; y: number; d: DistrictStat } | null>(null)

  const stats = useMemo(() => {
    const map = new Map<string, DistrictStat>()
    for (const d of snapshot?.districts ?? []) {
      const last7 = d.daily.slice(-7)
      map.set(norm(d.name), {
        name: d.name,
        rain7: last7.reduce((n, x) => n + x.precipitation_mm, 0),
        gustMax: Math.max(0, ...last7.map((x) => x.wind_gust_kmh)),
        notable: d.notable,
      })
    }
    return map
  }, [snapshot])

  const max = useMemo(() => Math.max(10, ...[...stats.values()].map((s) => s.rain7)), [stats])

  const { path, features } = useMemo(() => {
    const projection = geoMercator().fitExtent(
      [
        [18, 18],
        [W - 18, H - 18],
      ],
      geo as never,
    )
    return { path: geoPath(projection), features: geo.features }
  }, [geo])

  return (
    <div className="relative">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="h-auto w-full"
        role="img"
        aria-label="Tamil Nadu districts coloured by seven-day rainfall"
        onMouseLeave={() => setHover(null)}
      >
        <defs>
          <filter id="mapGlow" x="-20%" y="-20%" width="140%" height="140%">
            <feGaussianBlur stdDeviation="6" result="b" />
            <feMerge>
              <feMergeNode in="b" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        {features.map((f, i) => {
          const name = String(f.properties.district ?? f.properties.NAME_2 ?? `d${i}`)
          const stat = stats.get(norm(name))
          const ratio = stat ? clamp(stat.rain7 / max, 0, 1) : 0
          const strength = 8 + Math.round(ratio ** 0.75 * 78)
          const d = path(f as never) ?? undefined
          const active = hover?.d.name === stat?.name && Boolean(stat)
          return (
            <path
              key={`${name}-${i}`}
              d={d}
              fill={
                stat
                  ? `color-mix(in srgb, var(--sky) ${strength}%, var(--surface-inset))`
                  : 'var(--surface-inset)'
              }
              stroke={active ? 'var(--accent-hi)' : 'var(--line-strong)'}
              strokeWidth={active ? 1.6 : 0.7}
              style={{
                transition: 'fill 220ms ease-out, stroke 150ms ease-out',
                cursor: stat ? 'pointer' : 'default',
                filter: active ? 'url(#mapGlow)' : undefined,
              }}
              onMouseMove={(e) => {
                if (!stat) return
                const rect = (e.currentTarget.ownerSVGElement as SVGSVGElement).getBoundingClientRect()
                setHover({
                  x: ((e.clientX - rect.left) / rect.width) * 100,
                  y: ((e.clientY - rect.top) / rect.height) * 100,
                  d: stat,
                })
              }}
            />
          )
        })}
      </svg>

      {hover && (
        <div
          className="pointer-events-none absolute z-10 w-[228px] -translate-x-1/2 rounded-[10px] border p-3"
          style={{
            left: `${clamp(hover.x, 16, 84)}%`,
            top: `calc(${hover.y}% + 14px)`,
            background: 'var(--surface-3)',
            borderColor: 'var(--line-strong)',
            boxShadow: 'var(--pop-shadow)',
          }}
        >
          <div className="text-[13px] font-semibold">{hover.d.name}</div>
          <div className="mt-2 space-y-1 text-[11.5px]">
            <Row label="7-day rain" value={mm(hover.d.rain7)} color="var(--sky)" />
            <Row label="Max gust" value={kmh(hover.d.gustMax)} color="var(--violet)" />
          </div>
          {hover.d.notable.length > 0 && (
            <div className="mt-2 border-t pt-2" style={{ borderColor: 'var(--line)' }}>
              <div className="eyebrow mb-1">Notable days</div>
              {hover.d.notable.slice(0, 2).map((n) => (
                <div key={n} className="mono truncate text-[10.5px] text-[var(--fg-subtle)]">
                  {n}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* legend */}
      <div className="mt-2 flex items-center gap-3 px-1">
        <span className="eyebrow shrink-0">7-day rain</span>
        <div
          className="h-2 flex-1 rounded-full border"
          style={{
            borderColor: 'var(--line)',
            background:
              'linear-gradient(90deg, color-mix(in srgb, var(--sky) 8%, var(--surface-inset)), color-mix(in srgb, var(--sky) 86%, var(--surface-inset)))',
          }}
        />
        <span className="mono shrink-0 text-[11px] text-[var(--fg-subtle)]">0 – {nf(max, 0)} mm</span>
      </div>
    </div>
  )
}

function Row({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div className="flex items-center gap-2">
      <span className="size-1.5 rounded-full" style={{ background: color }} />
      <span className="text-[var(--fg-subtle)]">{label}</span>
      <span className="mono ml-auto font-medium">{value}</span>
    </div>
  )
}
