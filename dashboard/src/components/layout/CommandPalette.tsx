import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Command } from 'cmdk'
import { toast } from 'sonner'
import {
  BookOpenCheck,
  Copy,
  FileSearch,
  LayoutDashboard,
  Moon,
  PhoneCall,
  Radio,
  RefreshCw,
  ShieldCheck,
  Sun,
  Ticket as TicketIcon,
  Zap,
} from 'lucide-react'
import { useClaims, useTickets, useSetDataDown, useHealth } from '@/lib/api'
import { DEMO_PHONE, copyText, titleize } from '@/lib/utils'
import { useUi } from '@/store/ui'
import { Kbd } from '@/components/ui/base'

export function CommandPalette() {
  const open = useUi((s) => s.paletteOpen)
  const setOpen = useUi((s) => s.setPaletteOpen)
  const theme = useUi((s) => s.theme)
  const toggleTheme = useUi((s) => s.toggleTheme)
  const navigate = useNavigate()
  const { data: claims } = useClaims()
  const { data: tickets } = useTickets()
  const { data: health } = useHealth()
  const dataDown = useSetDataDown()

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key.toLowerCase() === 'k' && (e.metaKey || e.ctrlKey)) {
        e.preventDefault()
        setOpen(!open)
      }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open, setOpen])

  const run = (fn: () => void) => () => {
    setOpen(false)
    fn()
  }

  return (
    <Command.Dialog
      open={open}
      onOpenChange={setOpen}
      label="Command palette"
      className="fixed inset-0 z-[80]"
      shouldFilter
    >
      <div
        className="fixed inset-0 backdrop-blur-[3px]"
        style={{ background: 'var(--overlay)' }}
        onClick={() => setOpen(false)}
      />
      <div
        className="fixed top-[14vh] left-1/2 w-[calc(100vw-2rem)] max-w-[600px] -translate-x-1/2 overflow-hidden rounded-[14px] border"
        style={{
          background: 'var(--surface-1)',
          borderColor: 'var(--line-strong)',
          boxShadow: 'var(--pop-shadow)',
        }}
      >
        <div className="flex items-center gap-2.5 px-4" style={{ borderBottom: '1px solid var(--line)' }}>
          <Zap size={15} className="shrink-0 text-[var(--accent-fg)]" />
          <Command.Input
            autoFocus
            placeholder="Jump to a page, a claim, a ticket, or run an action…"
            className="h-12 w-full bg-transparent text-[14px] outline-none placeholder:text-[var(--fg-subtle)]"
          />
          <Kbd>esc</Kbd>
        </div>

        <Command.List className="max-h-[56vh] overflow-y-auto p-2">
          <Command.Empty className="px-3 py-8 text-center text-[13px] text-[var(--fg-subtle)]">
            Nothing matches that. Try a claim reference, a district, or “tickets”.
          </Command.Empty>

          <Group heading="Go to">
            <Item icon={<LayoutDashboard size={14} />} onSelect={run(() => navigate('/'))}>
              Overview
            </Item>
            <Item icon={<Radio size={14} />} onSelect={run(() => navigate('/live'))}>
              Live Desk
            </Item>
            <Item icon={<FileSearch size={14} />} onSelect={run(() => navigate('/claims'))}>
              Claims
            </Item>
            <Item icon={<TicketIcon size={14} />} onSelect={run(() => navigate('/tickets'))}>
              Tickets
            </Item>
            <Item icon={<BookOpenCheck size={14} />} onSelect={run(() => navigate('/knowledge'))}>
              Knowledge snapshot
            </Item>
            <Item icon={<ShieldCheck size={14} />} onSelect={run(() => navigate('/guardrails'))}>
              Guardrails & evals
            </Item>
          </Group>

          {claims && claims.length > 0 && (
            <Group heading="Claims">
              {claims.slice(0, 8).map((c) => (
                <Item
                  key={c.id}
                  icon={<FileSearch size={14} />}
                  value={`${c.reference} ${c.crop} ${c.location.district} ${c.farmer.name}`}
                  onSelect={run(() => navigate(`/claims/${c.id}`))}
                  right={titleize(c.status)}
                >
                  <span className="mono">{c.reference}</span>
                  <span className="ml-2 text-[var(--fg-subtle)]">
                    {titleize(c.crop)} · {c.location.district}
                  </span>
                </Item>
              ))}
            </Group>
          )}

          {tickets && tickets.length > 0 && (
            <Group heading="Tickets">
              {tickets.slice(0, 5).map((t) => (
                <Item
                  key={t.id}
                  icon={<TicketIcon size={14} />}
                  value={`${t.reference} ${t.severity} ${t.status}`}
                  onSelect={run(() => navigate('/tickets'))}
                  right={titleize(t.status)}
                >
                  <span className="mono">{t.reference}</span>
                  <span className="ml-2 text-[var(--fg-subtle)]">{titleize(t.severity)} severity</span>
                </Item>
              ))}
            </Group>
          )}

          <Group heading="Actions">
            <Item
              icon={<Copy size={14} />}
              onSelect={run(async () => {
                await copyText(DEMO_PHONE)
                toast.success('Demo number copied', { description: DEMO_PHONE })
              })}
            >
              Copy the demo phone number
            </Item>
            <Item
              icon={<PhoneCall size={14} />}
              onSelect={run(() => navigate('/live'))}
            >
              Open the Live Desk for a judge call
            </Item>
            <Item
              icon={<RefreshCw size={14} />}
              onSelect={run(() => navigate('/knowledge'))}
            >
              Refresh the knowledge snapshot
            </Item>
            <Item
              icon={theme === 'dark' ? <Sun size={14} /> : <Moon size={14} />}
              onSelect={run(toggleTheme)}
            >
              Switch to the {theme === 'dark' ? 'light' : 'dark'} theme
            </Item>
            <Item
              icon={<Zap size={14} />}
              onSelect={run(() => {
                const next = !health?.data_down_mode
                dataDown.mutate(next, {
                  onSuccess: () =>
                    toast(next ? 'Data-down mode on' : 'Data-down mode off', {
                      description: next
                        ? 'New claims will resolve to unverifiable and escalate.'
                        : 'The snapshot is treated as reachable again.',
                    }),
                })
              })}
            >
              {health?.data_down_mode ? 'Turn data-down mode off' : 'Turn data-down mode on'}
            </Item>
          </Group>
        </Command.List>
      </div>
    </Command.Dialog>
  )
}

function Group({ heading, children }: { heading: string; children: React.ReactNode }) {
  return (
    <Command.Group
      heading={heading}
      className="[&_[cmdk-group-heading]]:eyebrow mb-1 [&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:pt-2 [&_[cmdk-group-heading]]:pb-1.5"
    >
      {children}
    </Command.Group>
  )
}

function Item({
  icon,
  children,
  onSelect,
  value,
  right,
}: {
  icon: React.ReactNode
  children: React.ReactNode
  onSelect: () => void
  value?: string
  right?: string
}) {
  return (
    <Command.Item
      value={value}
      onSelect={onSelect}
      className="flex h-9 cursor-pointer items-center gap-2.5 rounded-[8px] px-2.5 text-[13px] text-[var(--fg-muted)] data-[selected=true]:bg-[var(--surface-3)] data-[selected=true]:text-[var(--fg)]"
    >
      <span className="shrink-0 opacity-70">{icon}</span>
      <span className="min-w-0 flex-1 truncate">{children}</span>
      {right && <span className="shrink-0 text-[11px] text-[var(--fg-subtle)]">{right}</span>}
    </Command.Item>
  )
}
