import { forwardRef, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import { toast } from 'sonner'
import {
  ArrowLeftRight,
  ArrowUpRight,
  CheckCircle2,
  CircleDot,
  Eye,
  Inbox,
  Ticket as TicketIcon,
} from 'lucide-react'
import type { Ticket, TicketStatus } from '@/types'
import { usePatchTicket, useTickets } from '@/lib/api'
import { RISK_TONE, TICKET_STATUS_LABEL, TICKET_STATUS_TONE } from '@/lib/tone'
import { ago, cn, fmtDateTime, titleize } from '@/lib/utils'
import { Badge, Button, EmptyState, Skeleton, toneVars } from '@/components/ui/base'
import { Drawer } from '@/components/ui/overlays'

const COLUMNS: { status: TicketStatus; label: string; icon: React.ReactNode; hint: string }[] = [
  { status: 'open', label: 'Open', icon: <CircleDot size={13} />, hint: 'Nobody has picked this up yet' },
  { status: 'in_review', label: 'In review', icon: <Eye size={13} />, hint: 'A reviewer is working on it' },
  { status: 'resolved', label: 'Resolved', icon: <CheckCircle2 size={13} />, hint: 'Closed with the farmer informed' },
]

export default function Tickets() {
  const { data, isLoading } = useTickets()
  const patch = usePatchTicket()
  const [open, setOpen] = useState<Ticket | null>(null)
  const [dragging, setDragging] = useState<number | null>(null)
  const [over, setOver] = useState<TicketStatus | null>(null)

  const grouped = useMemo(() => {
    const map: Record<TicketStatus, Ticket[]> = { open: [], in_review: [], resolved: [], rejected: [] }
    for (const t of data ?? []) map[t.status]?.push(t)
    return map
  }, [data])

  const move = (ticket: Ticket, status: TicketStatus) => {
    if (ticket.status === status) return
    patch.mutate(
      { id: ticket.id, status },
      {
        onSuccess: () =>
          toast.success(`${ticket.reference} → ${TICKET_STATUS_LABEL[status]}`, {
            description: 'Status pushed with PATCH /api/tickets/{id}',
          }),
      },
    )
  }

  return (
    <>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        {COLUMNS.map((col) => {
          const tickets = grouped[col.status] ?? []
          const t = toneVars[TICKET_STATUS_TONE[col.status]]
          return (
            <div
              key={col.status}
              onDragOver={(e) => {
                e.preventDefault()
                setOver(col.status)
              }}
              onDragLeave={() => setOver((s) => (s === col.status ? null : s))}
              onDrop={() => {
                const ticket = (data ?? []).find((x) => x.id === dragging)
                if (ticket) move(ticket, col.status)
                setDragging(null)
                setOver(null)
              }}
              className={cn(
                'flex min-h-[420px] flex-col rounded-[13px] border transition-colors duration-150',
                over === col.status && 'border-[var(--accent-line)]',
              )}
              style={{
                background: over === col.status ? 'var(--accent-soft)' : 'var(--surface-1)',
                borderColor: over === col.status ? 'var(--accent-line)' : 'var(--line)',
              }}
            >
              <div
                className="flex items-center gap-2 px-4 py-3"
                style={{ borderBottom: '1px solid var(--line)' }}
              >
                <span
                  className="grid size-6 place-items-center rounded-[7px] border"
                  style={{ color: t.fg, background: t.bg, borderColor: t.line }}
                >
                  {col.icon}
                </span>
                <span className="text-[13px] font-semibold">{col.label}</span>
                <Badge tone="neutral" mono className="ml-auto">
                  {tickets.length}
                </Badge>
              </div>

              <div className="flex-1 space-y-2 p-2.5">
                {isLoading ? (
                  Array.from({ length: 2 }).map((_, i) => (
                    <Skeleton key={i} className="h-[132px] rounded-[11px]" />
                  ))
                ) : tickets.length === 0 ? (
                  <EmptyState
                    icon={<Inbox size={16} />}
                    title={`Nothing ${col.label.toLowerCase()}`}
                    hint={col.hint}
                    className="py-12"
                  />
                ) : (
                  tickets.map((ticket) => (
                    <TicketCard
                      key={ticket.id}
                      ticket={ticket}
                      onOpen={() => setOpen(ticket)}
                      onMove={(s) => move(ticket, s)}
                      onDragStart={() => setDragging(ticket.id)}
                    />
                  ))
                )}
              </div>
            </div>
          )
        })}
      </div>

      <TicketSheet ticket={open} onOpenChange={(v) => !v && setOpen(null)} onMove={move} />
    </>
  )
}

type TicketCardProps = {
  ticket: Ticket
  onOpen: () => void
  onMove: (s: TicketStatus) => void
  onDragStart: () => void
}

const TicketCard = forwardRef<HTMLElement, TicketCardProps>(function TicketCard(
  { ticket, onOpen, onMove, onDragStart },
  ref,
) {
  const next: TicketStatus | null =
    ticket.status === 'open' ? 'in_review' : ticket.status === 'in_review' ? 'resolved' : null
  const prev: TicketStatus | null =
    ticket.status === 'resolved' ? 'in_review' : ticket.status === 'in_review' ? 'open' : null

  return (
    <motion.article
      ref={ref}
      layout
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
      draggable
      onDragStart={onDragStart}
      className="group cursor-grab rounded-[11px] border p-3 transition-colors duration-150 hover:border-[var(--line-strong)] active:cursor-grabbing"
      style={{ background: 'var(--surface-2)', borderColor: 'var(--line)' }}
    >
      <div className="mb-2 flex items-center gap-2">
        <Badge tone={RISK_TONE[ticket.severity]} dot>
          {titleize(ticket.severity)}
        </Badge>
        <span className="mono ml-auto text-[10.5px] text-[var(--fg-subtle)]">{ago(ticket.created_at)}</span>
      </div>

      <button onClick={onOpen} className="block w-full text-left">
        <div className="mono text-[12.5px] font-semibold">{ticket.reference}</div>
        <p className="mt-1.5 line-clamp-2 text-[12px] leading-relaxed text-[var(--fg-muted)]">
          {ticket.reasons[0]}
        </p>
        <p
          className="mt-2 line-clamp-2 rounded-[8px] border px-2 py-1.5 text-[11.5px] leading-relaxed text-[var(--fg-subtle)]"
          style={{ background: 'var(--surface-inset)', borderColor: 'var(--line)' }}
        >
          “{ticket.farmer_explanation}”
        </p>
      </button>

      <div className="mt-2.5 flex items-center gap-1.5">
        <Link
          to={`/claims/${ticket.claim_id}`}
          className="mono inline-flex h-6 items-center gap-1 rounded-[6px] border px-1.5 text-[10.5px] text-[var(--fg-subtle)] transition-colors hover:text-[var(--fg)]"
          style={{ borderColor: 'var(--line-strong)' }}
        >
          claim #{ticket.claim_id}
          <ArrowUpRight size={10} />
        </Link>
        <span className="ml-auto flex gap-1">
          {prev && (
            <Button size="xs" variant="ghost" onClick={() => onMove(prev)}>
              ← {TICKET_STATUS_LABEL[prev]}
            </Button>
          )}
          {next && (
            <Button size="xs" variant="subtle" onClick={() => onMove(next)}>
              {TICKET_STATUS_LABEL[next]} →
            </Button>
          )}
        </span>
      </div>
    </motion.article>
  )
})

function TicketSheet({
  ticket,
  onOpenChange,
  onMove,
}: {
  ticket: Ticket | null
  onOpenChange: (v: boolean) => void
  onMove: (t: Ticket, s: TicketStatus) => void
}) {
  return (
    <Drawer
      open={Boolean(ticket)}
      onOpenChange={onOpenChange}
      title={ticket ? ticket.reference : ''}
      description={
        ticket ? `${titleize(ticket.severity)} severity · created ${fmtDateTime(ticket.created_at)}` : ''
      }
      width={520}
    >
      {ticket && (
        <div className="space-y-4 p-5">
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={TICKET_STATUS_TONE[ticket.status]} dot>
              {TICKET_STATUS_LABEL[ticket.status]}
            </Badge>
            <Link
              to={`/claims/${ticket.claim_id}`}
              className="mono inline-flex items-center gap-1 text-[12px] text-[var(--accent-fg)] hover:underline"
            >
              open claim #{ticket.claim_id}
              <ArrowUpRight size={11} />
            </Link>
          </div>

          <section>
            <div className="eyebrow mb-2">Why it escalated</div>
            <ul className="space-y-1.5">
              {ticket.reasons.map((r) => (
                <li key={r} className="flex gap-2.5 text-[12.5px] leading-relaxed text-[var(--fg-muted)]">
                  <span className="mt-[7px] size-1 shrink-0 rounded-full bg-[var(--danger)]" aria-hidden />
                  {r}
                </li>
              ))}
            </ul>
          </section>

          <section
            className="rounded-[11px] border p-3.5"
            style={{ background: 'var(--accent-soft)', borderColor: 'var(--accent-line)' }}
          >
            <div className="eyebrow mb-1.5" style={{ color: 'var(--accent-fg)' }}>
              What we told the farmer
            </div>
            <p className="text-[12.5px] leading-relaxed">“{ticket.farmer_explanation}”</p>
          </section>

          {ticket.reviewer_notes && (
            <section>
              <div className="eyebrow mb-2">Reviewer notes</div>
              <p
                className="rounded-[10px] border px-3 py-2.5 text-[12.5px] leading-relaxed text-[var(--fg-muted)]"
                style={{ background: 'var(--surface-inset)', borderColor: 'var(--line)' }}
              >
                {ticket.reviewer_notes}
              </p>
            </section>
          )}

          <section>
            <div className="eyebrow mb-2">Move</div>
            <div className="flex flex-wrap gap-1.5">
              {(['open', 'in_review', 'resolved', 'rejected'] as TicketStatus[]).map((s) => (
                <Button
                  key={s}
                  size="sm"
                  variant={ticket.status === s ? 'primary' : 'subtle'}
                  icon={<ArrowLeftRight size={12} />}
                  onClick={() => onMove(ticket, s)}
                  disabled={ticket.status === s}
                >
                  {TICKET_STATUS_LABEL[s]}
                </Button>
              ))}
            </div>
          </section>

          <p className="flex items-center gap-1.5 text-[11px] text-[var(--fg-subtle)]">
            <TicketIcon size={11} />
            Ticket {ticket.reference} · call #{ticket.call_id} · updated {fmtDateTime(ticket.updated_at)}
          </p>
        </div>
      )}
    </Drawer>
  )
}
