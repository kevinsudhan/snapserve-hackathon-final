import { AnimatePresence, motion } from 'framer-motion'
import {
  CalendarDays,
  CloudLightning,
  Languages,
  MapPin,
  Ruler,
  Sprout,
  User,
} from 'lucide-react'
import type { Claim } from '@/types'
import { fmtDate, languageName, nf, titleize } from '@/lib/utils'
import { Badge, PanelHeader, Panel, toneVars } from '@/components/ui/base'
import { Tooltip } from '@/components/ui/overlays'

type Fact = {
  key: string
  label: string
  icon: React.ReactNode
  value: React.ReactNode
  hint?: React.ReactNode
  ready: boolean
}

/**
 * Each fact "checks in" with a staggered reveal as the extraction and the
 * gazetteer resolve — this is what the judges watch during a live call.
 */
export function IntakeFacts({ claim }: { claim: Claim }) {
  const loc = claim.location
  const confidence = loc.resolution_confidence
  /** the ingest pipeline has finished when evidence requirements or risk signals exist */
  const settled = claim.evidence_required.length > 0 || claim.risk.signals.length > 0 || Boolean(claim.escalation_reason)

  const facts: Fact[] = [
    {
      key: 'farmer',
      label: 'Caller',
      icon: <User size={13} />,
      value: claim.farmer.name ?? 'Not given',
      hint: claim.farmer.phone,
      ready: Boolean(claim.farmer.name || claim.farmer.phone),
    },
    {
      key: 'crop',
      label: 'Crop',
      icon: <Sprout size={13} />,
      value: titleize(claim.crop),
      hint: claim.crop_evidence?.season,
      ready: Boolean(claim.crop),
    },
    {
      key: 'land',
      label: 'Land extent',
      icon: <Ruler size={13} />,
      value: claim.land_extent
        ? `${nf(claim.land_extent.value, claim.land_extent.value % 1 ? 1 : 0)} ${claim.land_extent.unit}`
        : '—',
      hint: claim.land_extent ? `normalised to ${nf(claim.land_extent.hectares, 3)} ha` : undefined,
      ready: Boolean(claim.land_extent),
    },
    {
      key: 'damage',
      label: 'Damage type',
      icon: <CloudLightning size={13} />,
      value: titleize(claim.damage_type),
      ready: Boolean(claim.damage_type),
    },
    {
      key: 'event_date',
      label: 'Event date',
      icon: <CalendarDays size={13} />,
      value: fmtDate(claim.event_date),
      hint: `confidence ${Math.round(claim.event_date_confidence * 100)}%`,
      ready: Boolean(claim.event_date),
    },
    {
      key: 'location',
      label: 'Location',
      icon: <MapPin size={13} />,
      value: [loc.village, loc.taluk].filter(Boolean).join(', ') || loc.district || '—',
      hint: loc.district ? `${loc.district} district, ${loc.state}` : loc.state,
      ready: confidence > 0,
    },
    {
      key: 'language',
      label: 'Language',
      icon: <Languages size={13} />,
      value: languageName(claim.farmer.language),
      hint: claim.farmer.language,
      ready: Boolean(claim.farmer.language),
    },
  ]

  return (
    <Panel>
      <PanelHeader
        eyebrow="Step 1"
        title="Intake facts"
        icon={<Sprout size={14} />}
        tone="accent"
        right={
          confidence > 0 && (
            <Tooltip
              content={
                <span>
                  Location resolved offline by <span className="mono">{loc.resolved_by}</span>. Low
                  confidence falls back to the district centroid.
                </span>
              }
            >
              <span>
                <Badge tone={confidence > 0.85 ? 'ok' : confidence > 0.6 ? 'warn' : 'danger'} dot>
                  {Math.round(confidence * 100)}% location confidence
                </Badge>
              </span>
            </Tooltip>
          )
        }
      />
      <div className="grid grid-cols-2 gap-px overflow-hidden rounded-b-[12px] md:grid-cols-3 xl:grid-cols-4">
        <AnimatePresence initial={false}>
          {facts.map((f, i) => (
            <motion.div
              key={f.key}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.28, delay: Math.min(i * 0.045, 0.32), ease: [0.22, 1, 0.36, 1] }}
              className="relative px-5 py-3.5"
              style={{ boxShadow: '0 0 0 1px var(--line)' }}
            >
              <div className="mb-1.5 flex items-center gap-1.5">
                <span className="text-[var(--fg-subtle)]">{f.icon}</span>
                <span className="eyebrow">{f.label}</span>
              </div>
              {f.ready ? (
                <motion.div
                  initial={{ opacity: 0, filter: 'blur(3px)' }}
                  animate={{ opacity: 1, filter: 'blur(0px)' }}
                  transition={{ duration: 0.32, delay: Math.min(i * 0.045, 0.32) + 0.06 }}
                >
                  <div className="truncate text-[14px] font-semibold tracking-[-0.01em]">{f.value}</div>
                  {f.hint && (
                    <div className="mono mt-0.5 truncate text-[11px] text-[var(--fg-subtle)]">
                      {f.hint}
                    </div>
                  )}
                </motion.div>
              ) : settled ? (
                <NotCaptured />
              ) : (
                <PendingBar />
              )}
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </Panel>
  )
}

function PendingBar() {
  return (
    <div className="flex h-[34px] flex-col justify-center gap-1.5">
      <div
        className="relative h-2.5 w-3/5 overflow-hidden rounded-full"
        style={{ background: 'var(--surface-inset)' }}
      >
        <span
          className="absolute inset-y-0 w-1/3 rounded-full"
          style={{
            background: `linear-gradient(90deg, transparent, ${toneVars.accent.fg}, transparent)`,
            opacity: 0.35,
            animation: 'sweep 1.5s ease-in-out infinite',
          }}
        />
      </div>
      <div className="text-[10.5px] text-[var(--fg-subtle)]">listening…</div>
    </div>
  )
}

function NotCaptured() {
  return (
    <div className="flex h-[34px] flex-col justify-center">
      <div className="text-[13px] font-medium text-[var(--fg-subtle)]">Not captured</div>
      <div className="text-[10.5px] text-[var(--fg-subtle)]">reviewer to confirm</div>
    </div>
  )
}
