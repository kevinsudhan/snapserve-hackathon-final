import { ExternalLink, Quote } from 'lucide-react'
import type { Citation } from '@/types'
import { CITATION_TONE } from '@/lib/tone'
import { fmtDate } from '@/lib/utils'
import { toneVars } from '@/components/ui/base'
import { Popover } from '@/components/ui/overlays'

/**
 * Every fact the agent may speak carries one of these. Clicking opens the
 * exact quote, the publisher, the page and a link to the real document.
 */
export function CitationChip({ citation, compact }: { citation: Citation; compact?: boolean }) {
  const tone = toneVars[CITATION_TONE[citation.kind] ?? 'neutral']
  return (
    <Popover
      side="top"
      align="end"
      width={360}
      trigger={
        <button
          className="mono inline-flex h-[22px] shrink-0 items-center gap-1 rounded-[6px] border px-1.5 text-[10.5px] font-medium transition-[filter,transform] duration-150 hover:brightness-125 active:translate-y-px"
          style={{ color: tone.fg, background: tone.bg, borderColor: tone.line }}
          aria-label={`Citation ${citation.id}`}
        >
          {citation.id}
          {!compact && citation.page != null && (
            <span className="opacity-60">p.{citation.page}</span>
          )}
        </button>
      }
    >
      <div className="space-y-2.5">
        <div className="flex items-start gap-2">
          <span
            className="mono mt-px shrink-0 rounded-[5px] border px-1.5 py-0.5 text-[10px]"
            style={{ color: tone.fg, background: tone.bg, borderColor: tone.line }}
          >
            {citation.id}
          </span>
          <div className="min-w-0">
            <div className="text-[12.5px] leading-snug font-semibold">{citation.title}</div>
            <div className="mt-0.5 text-[11px] text-[var(--fg-subtle)]">{citation.publisher}</div>
          </div>
        </div>

        {citation.quote && (
          <blockquote
            className="rounded-[8px] border-l-2 py-2 pr-2 pl-2.5 text-[12px] leading-relaxed text-[var(--fg-muted)]"
            style={{ background: 'var(--surface-inset)', borderColor: tone.fg }}
          >
            <Quote size={11} className="mr-1 -mt-0.5 inline opacity-45" />
            {citation.quote}
          </blockquote>
        )}

        <div className="flex items-center justify-between gap-3 text-[11px] text-[var(--fg-subtle)]">
          <span className="num">
            {citation.page != null ? `Page ${citation.page} · ` : ''}as of {fmtDate(citation.as_of)}
          </span>
          <a
            href={citation.url}
            target="_blank"
            rel="noreferrer noopener"
            className="inline-flex items-center gap-1 font-medium text-[var(--accent-fg)] hover:underline"
          >
            Open source
            <ExternalLink size={11} />
          </a>
        </div>
      </div>
    </Popover>
  )
}
