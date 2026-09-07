import { useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import { AnimatePresence, motion } from 'framer-motion'
import {
  Camera,
  Check,
  CheckCircle2,
  Loader2,
  MapPin,
  RotateCcw,
  ShieldCheck,
  Sprout,
} from 'lucide-react'
import type { EvidencePortalItem } from '@/types'
import { useEvidencePortal, useUploadEvidence } from '@/lib/api'
import { cn, fmtDate, languageName } from '@/lib/utils'
import { useUi } from '@/store/ui'

type UploadState = {
  status: 'idle' | 'uploading' | 'done' | 'error'
  progress: number
  preview?: string
}

/**
 * Public, chrome-free page the farmer opens from a WhatsApp link.
 * Light theme, one column, 48 px touch targets, no jargon.
 */
export default function EvidencePage() {
  const { token } = useParams()
  const { data, isLoading, isError } = useEvidencePortal(token)
  const setTheme = useUi((s) => s.setTheme)
  const [coords, setCoords] = useState<{ lat: number; lon: number } | null>(null)
  const [states, setStates] = useState<Record<string, UploadState>>({})

  /* the farmer's page is always light — restore the reviewer's theme on exit */
  useEffect(() => {
    const previous = document.documentElement.getAttribute('data-theme')
    document.documentElement.setAttribute('data-theme', 'light')
    return () => {
      if (previous) document.documentElement.setAttribute('data-theme', previous)
      else setTheme('dark')
    }
  }, [setTheme])

  useEffect(() => {
    if (!navigator.geolocation) return
    navigator.geolocation.getCurrentPosition(
      (p) => setCoords({ lat: p.coords.latitude, lon: p.coords.longitude }),
      () => setCoords(null),
      { enableHighAccuracy: false, timeout: 8000, maximumAge: 600_000 },
    )
  }, [])

  const required = data?.items.filter((i) => i.required) ?? []
  const doneCount = required.filter(
    (i) => i.uploaded.length > 0 || states[i.key]?.status === 'done',
  ).length
  const allDone = required.length > 0 && doneCount === required.length

  if (isLoading) {
    return (
      <Frame>
        <div className="space-y-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="skeleton h-[104px] rounded-[14px]" />
          ))}
        </div>
      </Frame>
    )
  }

  if (isError || !data) {
    return (
      <Frame>
        <div className="rounded-[14px] border bg-white p-6 text-center" style={{ borderColor: 'var(--line)' }}>
          <p className="text-[15px] font-semibold">This link is no longer valid</p>
          <p className="mt-2 text-[13px] text-[var(--fg-muted)]">
            Please call the help desk again and ask for a new photo link.
          </p>
        </div>
      </Frame>
    )
  }

  return (
    <Frame>
      {/* header */}
      <header className="mb-4">
        <div className="mb-3 flex items-center gap-2.5">
          <span
            className="grid size-8 place-items-center rounded-[10px]"
            style={{ background: 'linear-gradient(160deg, var(--accent-hi), var(--accent))' }}
          >
            <Sprout size={16} color="#fff" />
          </span>
          <div>
            <div className="text-[15px] leading-none font-semibold tracking-[-0.02em]">Araxys Desk</div>
            <div className="mt-1 text-[11px] leading-none text-[var(--fg-subtle)]">
              Photos for your crop claim
            </div>
          </div>
        </div>

        <div
          className="rounded-[14px] border p-4"
          style={{ background: '#fff', borderColor: 'var(--line)' }}
        >
          <div className="flex items-center justify-between gap-3">
            <div className="min-w-0">
              <div className="text-[11px] tracking-[0.08em] text-[var(--fg-subtle)] uppercase">
                Claim reference
              </div>
              <div className="mono mt-1 text-[17px] font-semibold">{data.claim_reference}</div>
            </div>
            <div className="shrink-0 text-right">
              <div className="text-[11px] text-[var(--fg-subtle)]">
                {languageName(data.farmer_language)}
              </div>
              <div className="text-[11px] text-[var(--fg-subtle)]">
                open until {fmtDate(data.expires_at)}
              </div>
            </div>
          </div>

          <div className="mt-3.5">
            <div className="mb-1.5 flex items-center justify-between text-[12px]">
              <span className="text-[var(--fg-muted)]">
                {doneCount} of {required.length} needed photos
              </span>
              <span className="mono font-semibold" style={{ color: 'var(--accent)' }}>
                {required.length ? Math.round((doneCount / required.length) * 100) : 0}%
              </span>
            </div>
            <div
              className="h-2.5 overflow-hidden rounded-full"
              style={{ background: 'var(--surface-inset)' }}
            >
              <motion.div
                className="h-full rounded-full"
                style={{ background: 'linear-gradient(90deg, var(--accent-hi), var(--accent))' }}
                initial={{ width: 0 }}
                animate={{ width: `${required.length ? (doneCount / required.length) * 100 : 0}%` }}
                transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
              />
            </div>
          </div>
        </div>
      </header>

      <AnimatePresence>
        {allDone && (
          <motion.div
            initial={{ opacity: 0, y: -8, height: 0 }}
            animate={{ opacity: 1, y: 0, height: 'auto' }}
            className="mb-4 overflow-hidden"
          >
            <div
              className="flex items-start gap-3 rounded-[14px] border p-4"
              style={{ background: 'var(--accent-soft)', borderColor: 'var(--accent-line)' }}
            >
              <CheckCircle2 size={20} style={{ color: 'var(--accent)' }} className="mt-px shrink-0" />
              <div>
                <p className="text-[14px] font-semibold">All done — thank you.</p>
                <p className="mt-1 text-[12.5px] leading-relaxed text-[var(--fg-muted)]">
                  Your photos have reached the team. Someone will contact you if anything else is needed.
                  You can send more photos any time using this same link.
                </p>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <ul className="space-y-3">
        {data.items.map((item) => (
          <EvidenceCard
            key={item.key}
            item={item}
            token={token ?? ''}
            coords={coords}
            state={states[item.key]}
            onState={(s) => setStates((prev) => ({ ...prev, [item.key]: s }))}
          />
        ))}
      </ul>

      <footer className="mt-6 space-y-2 pb-8 text-center">
        <p className="flex items-center justify-center gap-1.5 text-[11.5px] text-[var(--fg-subtle)]">
          <ShieldCheck size={12} />
          Your photos are used only to assess this claim.
        </p>
        {coords && (
          <p className="mono flex items-center justify-center gap-1.5 text-[11px] text-[var(--fg-subtle)]">
            <MapPin size={11} />
            location shared with each photo
          </p>
        )}
        <p className="text-[11.5px] text-[var(--fg-subtle)]">
          Trouble uploading? Call the helpline 14447.
        </p>
      </footer>
    </Frame>
  )
}

function Frame({ children }: { children: React.ReactNode }) {
  return (
    <div
      className="min-h-dvh w-full"
      style={{
        background:
          'linear-gradient(180deg, color-mix(in srgb, var(--accent) 7%, #f5f7fa) 0%, #f5f7fa 220px)',
      }}
    >
      <div className="mx-auto w-full max-w-[520px] px-4 pt-5">{children}</div>
    </div>
  )
}

function EvidenceCard({
  item,
  token,
  coords,
  state,
  onState,
}: {
  item: EvidencePortalItem
  token: string
  coords: { lat: number; lon: number } | null
  state?: UploadState
  onState: (s: UploadState) => void
}) {
  const inputRef = useRef<HTMLInputElement>(null)
  const upload = useUploadEvidence(token)
  const uploaded = item.uploaded.length > 0 || state?.status === 'done'
  const label = item.label_local || item.label

  const pick = (file: File) => {
    const preview = URL.createObjectURL(file)
    onState({ status: 'uploading', progress: 0.02, preview })
    upload.mutate(
      {
        itemKey: item.key,
        file,
        lat: coords?.lat,
        lon: coords?.lon,
        onProgress: (p) => onState({ status: 'uploading', progress: p, preview }),
      },
      {
        onSuccess: () => onState({ status: 'done', progress: 1, preview }),
        onError: () => onState({ status: 'error', progress: 0, preview }),
      },
    )
  }

  return (
    <motion.li
      layout
      className="overflow-hidden rounded-[14px] border"
      style={{
        background: '#fff',
        borderColor: uploaded ? 'var(--accent-line)' : 'var(--line)',
      }}
    >
      <div className="flex items-start gap-3 p-4">
        <span
          className="mt-0.5 grid size-6 shrink-0 place-items-center rounded-full border transition-colors duration-200"
          style={{
            background: uploaded ? 'var(--accent)' : 'transparent',
            borderColor: uploaded ? 'var(--accent)' : 'var(--line-strong)',
            color: '#fff',
          }}
        >
          {uploaded && <Check size={13} strokeWidth={3} />}
        </span>

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[15px] leading-snug font-semibold">{label}</span>
            {item.required ? (
              <span
                className="rounded-full px-2 py-0.5 text-[10.5px] font-semibold"
                style={{ background: 'var(--accent-soft)', color: 'var(--accent)' }}
              >
                needed
              </span>
            ) : (
              <span
                className="rounded-full px-2 py-0.5 text-[10.5px] font-semibold"
                style={{ background: 'var(--neutral-soft)', color: 'var(--fg-subtle)' }}
              >
                optional
              </span>
            )}
          </div>
          {item.label_local && item.label !== item.label_local && (
            <div className="mt-0.5 text-[12.5px] text-[var(--fg-muted)]">{item.label}</div>
          )}
          {item.instructions_local && (
            <p className="mt-1.5 text-[12.5px] leading-relaxed text-[var(--fg-subtle)]">
              {item.instructions_local}
            </p>
          )}
        </div>
      </div>

      {(state?.preview || item.uploaded[0]?.url) && (
        <div className="relative mx-4 mb-3 overflow-hidden rounded-[11px]" style={{ background: 'var(--surface-inset)' }}>
          <img
            src={state?.preview ?? item.uploaded[0]?.url}
            alt={label}
            className="h-[168px] w-full object-cover"
          />
          {state?.status === 'uploading' && (
            <div className="absolute inset-0 grid place-items-center" style={{ background: 'rgba(6,14,20,0.55)' }}>
              <div className="flex flex-col items-center gap-2 text-white">
                <Loader2 size={22} className="animate-spin" />
                <span className="mono text-[12px]">{Math.round((state.progress ?? 0) * 100)}%</span>
              </div>
            </div>
          )}
          {state?.status === 'done' && (
            <motion.span
              initial={{ scale: 0.6, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              className="absolute top-2 right-2 grid size-7 place-items-center rounded-full"
              style={{ background: 'var(--accent)' }}
            >
              <Check size={15} color="#fff" strokeWidth={3} />
            </motion.span>
          )}
        </div>
      )}

      <div className="flex gap-2 px-4 pb-4">
        <input
          ref={inputRef}
          type="file"
          accept="image/*"
          capture="environment"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0]
            if (file) pick(file)
            e.target.value = ''
          }}
        />
        <button
          onClick={() => inputRef.current?.click()}
          disabled={state?.status === 'uploading'}
          className={cn(
            'flex h-12 flex-1 items-center justify-center gap-2 rounded-[11px] text-[14px] font-semibold transition-transform duration-150 active:scale-[0.99]',
          )}
          style={
            uploaded
              ? { background: 'var(--surface-inset)', color: 'var(--fg-muted)', border: '1px solid var(--line-strong)' }
              : {
                  background: 'linear-gradient(180deg, var(--accent-hi), var(--accent))',
                  color: '#fff',
                  boxShadow: '0 8px 22px -12px var(--accent)',
                }
          }
        >
          {uploaded ? <RotateCcw size={16} /> : <Camera size={17} />}
          {uploaded ? 'Take another' : 'Take photo'}
        </button>
      </div>

      {state?.status === 'error' && (
        <p className="px-4 pb-4 text-[12.5px]" style={{ color: 'var(--danger)' }}>
          That did not upload. Please check your network and try again.
        </p>
      )}
    </motion.li>
  )
}
