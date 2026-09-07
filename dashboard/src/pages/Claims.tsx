import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { FileSearch, Search, SlidersHorizontal, X } from 'lucide-react'
import type { Claim, ClaimStatus } from '@/types'
import { useClaims } from '@/lib/api'
import {
  CLAIM_STATUS_LABEL,
  CLAIM_STATUS_TONE,
  RISK_TONE,
  VERDICT_LABEL,
  VERDICT_TONE,
} from '@/lib/tone'
import { ago, cn, languageName, nf, titleize } from '@/lib/utils'
import { Badge, Chip, EmptyState, Panel, Skeleton } from '@/components/ui/base'

const STATUSES: (ClaimStatus | 'all')[] = [
  'all',
  'logged',
  'escalated',
  'under_review',
  'approved_for_survey',
  'closed',
]

export default function Claims() {
  const [q, setQ] = useState('')
  const [status, setStatus] = useState<ClaimStatus | 'all'>('all')
  const { data, isLoading } = useClaims()
  const navigate = useNavigate()

  const rows = useMemo(() => {
    let out = data ?? []
    if (status !== 'all') out = out.filter((c) => c.status === status)
    const needle = q.trim().toLowerCase()
    if (needle) {
      out = out.filter((c) =>
        [
          c.reference,
          c.crop,
          c.damage_type,
          c.farmer.name,
          c.farmer.phone,
          c.location.village,
          c.location.taluk,
          c.location.district,
        ]
          .filter(Boolean)
          .some((v) => String(v).toLowerCase().includes(needle)),
      )
    }
    return out
  }, [data, status, q])

  const counts = useMemo(() => {
    const map: Record<string, number> = { all: data?.length ?? 0 }
    for (const c of data ?? []) map[c.status] = (map[c.status] ?? 0) + 1
    return map
  }, [data])

  return (
    <div className="space-y-4">
      <Panel className="flex flex-wrap items-center gap-3 px-4 py-3">
        <div
          className="flex h-8 min-w-[240px] flex-1 items-center gap-2 rounded-[9px] border px-2.5"
          style={{ background: 'var(--surface-inset)', borderColor: 'var(--line)' }}
        >
          <Search size={14} className="shrink-0 text-[var(--fg-subtle)]" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search reference, farmer, crop, village, district…"
            className="h-full w-full bg-transparent text-[13px] outline-none placeholder:text-[var(--fg-subtle)]"
          />
          {q && (
            <button
              onClick={() => setQ('')}
              aria-label="Clear search"
              className="shrink-0 text-[var(--fg-subtle)] hover:text-[var(--fg)]"
            >
              <X size={13} />
            </button>
          )}
        </div>

        {/* Wraps instead of running off the edge. Six status filters plus
          * their counts need more width than a phone has, and a chip you
          * cannot see is a filter you do not know exists. */}
        <div className="flex flex-wrap items-center gap-1.5">
          <SlidersHorizontal size={13} className="mr-1 shrink-0 text-[var(--fg-muted)]" />
          {STATUSES.map((s) => (
            <Chip key={s} active={status === s} onClick={() => setStatus(s)}>
              {s === 'all' ? 'All' : CLAIM_STATUS_LABEL[s]}
              <span className="mono ml-0.5 opacity-70">{counts[s] ?? 0}</span>
            </Chip>
          ))}
        </div>
      </Panel>

      {/*
        The seven columns need about 890px of minimum width, which a phone
        does not have. Without a scroller of its own the grid simply forced
        the document wider and the whole page slid sideways, taking the top
        bar with it. Now the table scrolls inside its own card and the page
        never scrolls horizontally at any width.
      */}
      <Panel className="overflow-hidden">
        <div className="overflow-x-auto overscroll-x-contain">
        <div className="min-w-[890px]">
        <div
          className="grid grid-cols-[minmax(120px,1.1fr)_minmax(140px,1.3fr)_minmax(120px,1fr)_minmax(120px,1fr)_100px_92px_88px] items-center gap-3 px-5 py-2.5"
          style={{ borderBottom: '1px solid var(--line)', background: 'var(--surface-inset)' }}
        >
          {['Reference', 'Farmer & location', 'Crop / damage', 'Weather verdict', 'Risk', 'Language', 'Status'].map(
            (h) => (
              <span key={h} className="eyebrow truncate">
                {h}
              </span>
            ),
          )}
        </div>

        {isLoading ? (
          <div className="space-y-1 p-3">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-[52px] rounded-[9px]" />
            ))}
          </div>
        ) : rows.length === 0 ? (
          <EmptyState
            icon={<FileSearch size={17} />}
            title="No claims match that"
            hint="Clear the search or pick a different status — every intake from every call lands here."
          />
        ) : (
          <ul>
            {rows.map((c, i) => (
              <ClaimRow key={c.id} claim={c} index={i} onClick={() => navigate(`/claims/${c.id}`)} />
            ))}
          </ul>
        )}
        </div>
        </div>
      </Panel>
    </div>
  )
}

function ClaimRow({ claim, index, onClick }: { claim: Claim; index: number; onClick: () => void }) {
  const v = claim.weather_evidence.verdict
  return (
    <motion.li
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.22, delay: Math.min(index * 0.03, 0.3) }}
    >
      <button
        onClick={onClick}
        className={cn(
          'grid w-full grid-cols-[minmax(120px,1.1fr)_minmax(140px,1.3fr)_minmax(120px,1fr)_minmax(120px,1fr)_100px_92px_88px] items-center gap-3 px-5 py-3 text-left',
          'transition-colors duration-150 hover:bg-[var(--surface-2)]',
        )}
        style={{ borderBottom: '1px solid var(--line)' }}
      >
        <span className="min-w-0">
          <span className="mono block truncate text-[12.5px] font-semibold">{claim.reference}</span>
          <span className="block truncate text-[11px] text-[var(--fg-subtle)]">
            {ago(claim.created_at)}
          </span>
        </span>

        <span className="min-w-0">
          <span className="block truncate text-[12.5px]">{claim.farmer.name ?? 'Not given'}</span>
          <span className="block truncate text-[11px] text-[var(--fg-subtle)]">
            {[claim.location.village, claim.location.district].filter(Boolean).join(', ')}
          </span>
        </span>

        <span className="min-w-0">
          <span className="block truncate text-[12.5px]">{titleize(claim.crop)}</span>
          <span className="block truncate text-[11px] text-[var(--fg-subtle)]">
            {titleize(claim.damage_type)}
            {claim.land_extent ? ` · ${nf(claim.land_extent.hectares, 2)} ha` : ''}
          </span>
        </span>

        <span className="min-w-0">
          <Badge tone={VERDICT_TONE[v]} dot>
            {VERDICT_LABEL[v]}
          </Badge>
        </span>

        <span className="min-w-0">
          <Badge tone={RISK_TONE[claim.risk.level]} mono>
            {claim.risk.score}
            <span className="opacity-60">/100</span>
          </Badge>
        </span>

        <span className="min-w-0 truncate text-[12px] text-[var(--fg-muted)]">
          {languageName(claim.farmer.language)}
        </span>

        <span className="min-w-0">
          <Badge tone={CLAIM_STATUS_TONE[claim.status]}>{CLAIM_STATUS_LABEL[claim.status]}</Badge>
        </span>
      </button>
    </motion.li>
  )
}
