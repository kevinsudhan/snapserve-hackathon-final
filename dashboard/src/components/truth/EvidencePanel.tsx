import { useMemo, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { toast } from 'sonner'
import {
  Camera,
  Check,
  Copy,
  ImageIcon,
  Link2,
  MapPin,
  MessageCircle,
  QrCode,
} from 'lucide-react'
import type { Claim, EvidenceFile } from '@/types'
import { useEvidenceLink } from '@/lib/api'
import { copyText, fmtDateTime, nf } from '@/lib/utils'
import { Badge, Button, EmptyState, Panel, PanelHeader, ProgressBar, toneVars } from '@/components/ui/base'
import { Modal, Tooltip } from '@/components/ui/overlays'
import type { EvidenceLink } from '@/types'

export function EvidencePanel({ claim }: { claim: Claim }) {
  const [linkOpen, setLinkOpen] = useState(false)
  const [link, setLink] = useState<EvidenceLink | null>(null)
  const createLink = useEvidenceLink()

  const byKey = useMemo(() => {
    const map = new Map<string, EvidenceFile[]>()
    for (const f of claim.evidence_uploads) {
      map.set(f.item_key, [...(map.get(f.item_key) ?? []), f])
    }
    return map
  }, [claim.evidence_uploads])

  const required = claim.evidence_required.filter((i) => i.required)
  const done = required.filter((i) => (byKey.get(i.key)?.length ?? 0) > 0).length
  const progress = required.length ? done / required.length : 0

  const openLink = () => {
    createLink.mutate(claim.id, {
      onSuccess: (data) => {
        setLink(data)
        setLinkOpen(true)
      },
      onError: () => toast.error('Could not create an evidence link'),
    })
  }

  return (
    <>
      <Panel>
        <PanelHeader
          eyebrow="Step 7"
          title="Evidence"
          icon={<Camera size={14} />}
          tone="accent"
          right={
            <Button
              variant="primary"
              icon={<QrCode size={14} />}
              onClick={openLink}
              disabled={createLink.isPending}
            >
              {createLink.isPending ? 'Creating…' : 'Send evidence link'}
            </Button>
          }
        />

        {claim.evidence_required.length === 0 ? (
          <EmptyState
            icon={<Camera size={17} />}
            title="Checklist not built yet"
            hint="The checklist comes from the damage type and the crop, with a citation for each item."
            className="py-9"
          />
        ) : (
          <>
            <div className="flex items-center gap-3 px-5 pb-3">
              <ProgressBar value={progress} tone={progress === 1 ? 'ok' : 'accent'} className="flex-1" />
              <span className="mono shrink-0 text-[11.5px] text-[var(--fg-subtle)]">
                {done}/{required.length} required
              </span>
            </div>

            <ul className="px-5 pb-5">
              {claim.evidence_required.map((item, i) => {
                const files = byKey.get(item.key) ?? []
                const complete = files.length > 0
                return (
                  <motion.li
                    key={item.key}
                    initial={{ opacity: 0, y: 6 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.22, delay: i * 0.04 }}
                    className="flex items-start gap-3 py-2.5"
                    style={{ borderTop: i === 0 ? 'none' : '1px solid var(--line)' }}
                  >
                    <span
                      className="mt-0.5 grid size-[18px] shrink-0 place-items-center rounded-full border transition-colors duration-200"
                      style={{
                        background: complete ? 'var(--ok-soft)' : 'transparent',
                        borderColor: complete ? toneVars.ok.line : 'var(--line-strong)',
                        color: 'var(--ok)',
                      }}
                    >
                      {complete && <Check size={11} strokeWidth={3} />}
                    </span>

                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-[13px] font-medium">{item.label}</span>
                        {item.required ? (
                          <Badge tone="neutral">required</Badge>
                        ) : (
                          <Badge tone="neutral">optional</Badge>
                        )}
                      </div>
                      {item.label_local && (
                        <div className="mt-0.5 text-[12px] text-[var(--fg-subtle)]">{item.label_local}</div>
                      )}
                      <div className="mt-0.5 text-[11.5px] text-[var(--fg-subtle)]">{item.why}</div>

                      <AnimatePresence>
                        {files.length > 0 && (
                          <motion.div
                            initial={{ opacity: 0, height: 0 }}
                            animate={{ opacity: 1, height: 'auto' }}
                            className="mt-2 flex flex-wrap gap-2"
                          >
                            {files.map((f) => (
                              <Thumb key={f.id} file={f} />
                            ))}
                          </motion.div>
                        )}
                      </AnimatePresence>
                    </div>
                  </motion.li>
                )
              })}
            </ul>
          </>
        )}
      </Panel>

      <Modal
        open={linkOpen}
        onOpenChange={setLinkOpen}
        title="Evidence upload link"
        description={`Sent to the farmer over WhatsApp for claim ${claim.reference}. Photos land here live.`}
        size="md"
        footer={
          <>
            <Button variant="ghost" onClick={() => setLinkOpen(false)}>
              Close
            </Button>
            {link && (
              <Button
                variant="primary"
                icon={<MessageCircle size={14} />}
                onClick={() => window.open(link.whatsapp_url, '_blank', 'noopener')}
              >
                Open WhatsApp
              </Button>
            )}
          </>
        }
      >
        {link && (
          <div className="space-y-4">
            <div className="flex flex-col items-center gap-3 sm:flex-row sm:items-start">
              <div
                className="grid size-[164px] shrink-0 place-items-center rounded-[12px] border p-2.5"
                style={{ background: '#ffffff', borderColor: 'var(--line-strong)' }}
              >
                <div
                  className="size-full [&>svg]:size-full"
                  // the backend returns a real qrcode-generated SVG string
                  dangerouslySetInnerHTML={{ __html: link.qr_svg }}
                />
              </div>
              <div className="min-w-0 flex-1 space-y-2.5">
                <div>
                  <div className="eyebrow mb-1.5">Link</div>
                  <div
                    className="flex items-center gap-2 rounded-[9px] border px-2.5 py-2"
                    style={{ background: 'var(--surface-inset)', borderColor: 'var(--line)' }}
                  >
                    <Link2 size={13} className="shrink-0 text-[var(--fg-subtle)]" />
                    <span className="mono min-w-0 flex-1 truncate text-[11.5px]">{link.url}</span>
                    <Tooltip content="Copy link">
                      <button
                        className="shrink-0 text-[var(--fg-subtle)] hover:text-[var(--fg)]"
                        onClick={async () => {
                          await copyText(link.url)
                          toast.success('Link copied')
                        }}
                        aria-label="Copy link"
                      >
                        <Copy size={13} />
                      </button>
                    </Tooltip>
                  </div>
                </div>
                <p className="text-[11.5px] leading-relaxed text-[var(--fg-subtle)]">
                  Opens in WhatsApp’s in-app browser, in the caller’s language, with a camera button per
                  item. Expires {fmtDateTime(link.expires_at)}.
                </p>
                <a
                  href={link.url}
                  target="_blank"
                  rel="noreferrer noopener"
                  className="inline-flex items-center gap-1.5 text-[12px] font-medium text-[var(--accent-fg)] hover:underline"
                >
                  Preview the farmer’s page
                </a>
              </div>
            </div>

            <div>
              <div className="eyebrow mb-2">Uploaded so far</div>
              {claim.evidence_uploads.length === 0 ? (
                <div
                  className="rounded-[10px] border px-3 py-4 text-center text-[12px] text-[var(--fg-subtle)]"
                  style={{ background: 'var(--surface-inset)', borderColor: 'var(--line)' }}
                >
                  Nothing yet — photos appear here the moment the farmer uploads them.
                </div>
              ) : (
                <div className="flex flex-wrap gap-2">
                  {claim.evidence_uploads.map((f) => (
                    <Thumb key={f.id} file={f} />
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </Modal>
    </>
  )
}

export function Thumb({ file }: { file: EvidenceFile }) {
  const [broken, setBroken] = useState(!file.url)
  return (
    <Tooltip
      content={
        <div className="space-y-0.5">
          <div className="mono">{file.filename}</div>
          <div className="text-[var(--fg-subtle)]">{fmtDateTime(file.uploaded_at)}</div>
          <div className="text-[var(--fg-subtle)]">{nf(file.size / 1024 / 1024, 1)} MB</div>
          {file.lat != null && (
            <div className="mono text-[var(--fg-subtle)]">
              {nf(file.lat, 4)}, {nf(file.lon ?? 0, 4)}
            </div>
          )}
        </div>
      }
    >
      <motion.div
        initial={{ opacity: 0, scale: 0.9 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.24, ease: [0.22, 1, 0.36, 1] }}
        className="relative size-[62px] overflow-hidden rounded-[9px] border"
        style={{ background: 'var(--surface-inset)', borderColor: 'var(--line-strong)' }}
      >
        {broken ? (
          <div className="grid size-full place-items-center text-[var(--fg-subtle)]">
            <ImageIcon size={16} />
          </div>
        ) : (
          <img
            src={file.url}
            alt={file.filename}
            className="size-full object-cover"
            onError={() => setBroken(true)}
          />
        )}
        {file.lat != null && (
          <span
            className="absolute right-1 bottom-1 grid size-[15px] place-items-center rounded-full"
            style={{ background: 'rgba(0,0,0,0.55)', color: '#fff' }}
          >
            <MapPin size={9} />
          </span>
        )}
        {file.quality_flag === 'blurry' && (
          <span
            className="absolute inset-x-0 top-0 py-px text-center text-[9px] font-semibold"
            style={{ background: 'var(--warn)', color: '#1a1300' }}
          >
            blurry
          </span>
        )}
      </motion.div>
    </Tooltip>
  )
}
