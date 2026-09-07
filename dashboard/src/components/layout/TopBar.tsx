import { useLocation } from 'react-router-dom'
import { AlertTriangle, FlaskConical, Menu, Moon, Search, Sun } from 'lucide-react'
import { useHealth } from '@/lib/api'
import { MOCK, ago, cn } from '@/lib/utils'
import { useUi } from '@/store/ui'
import { useLive } from '@/store/live'
import { Badge, IconButton, Kbd, LiveDot } from '@/components/ui/base'
import { Tooltip } from '@/components/ui/overlays'

const TITLES: Record<string, { title: string; sub: string }> = {
  '/': { title: 'Overview', sub: 'What the desk has handled today' },
  '/live': { title: 'Live Desk', sub: 'Calls in flight and the truth check as it builds' },
  '/claims': { title: 'Claims', sub: 'Every intake with its evidence and citations' },
  '/tickets': { title: 'Tickets', sub: 'Escalations waiting on a person' },
  '/knowledge': { title: 'Knowledge', sub: 'The snapshot the agent is allowed to quote' },
  '/guardrails': { title: 'Guardrails', sub: 'Promise leaks, fabrications and the red-team scoreboard' },
}

export function TopBar() {
  const { pathname } = useLocation()
  const setPaletteOpen = useUi((s) => s.setPaletteOpen)
  const setNavOpen = useUi((s) => s.setNavOpen)
  const theme = useUi((s) => s.theme)
  const toggleTheme = useUi((s) => s.toggleTheme)
  const status = useLive((s) => s.status)
  const lastEventAt = useLive((s) => s.lastEventAt)
  const { data: health } = useHealth()

  const key = pathname.startsWith('/claims')
    ? '/claims'
    : pathname.startsWith('/tickets')
      ? '/tickets'
      : (TITLES[pathname] ? pathname : '/')
  const meta = TITLES[key]

  const wsTone =
    status === 'open' ? 'ok' : status === 'reconnecting' || status === 'connecting' ? 'warn' : 'danger'
  const wsLabel =
    status === 'open'
      ? 'Live'
      : status === 'connecting'
        ? 'Connecting'
        : status === 'reconnecting'
          ? 'Reconnecting'
          : 'Offline'

  return (
    <header
      className="sticky top-0 z-30 flex h-14 shrink-0 items-center gap-3 px-3 sm:gap-4 sm:px-5"
      style={{
        borderBottom: '1px solid var(--line)',
        background: 'color-mix(in srgb, var(--bg) 82%, transparent)',
        backdropFilter: 'blur(14px) saturate(140%)',
      }}
    >
      {/* The only way into the navigation once the rail becomes a drawer. */}
      <button
        onClick={() => setNavOpen(true)}
        aria-label="Open navigation"
        className="-ml-1 grid size-8 shrink-0 place-items-center rounded-[8px] text-[var(--fg-muted)] transition-colors hover:bg-[var(--surface-3)] hover:text-[var(--fg)] lg:hidden"
      >
        <Menu size={17} />
      </button>

      <div className="min-w-0">
        <h1 className="truncate text-[14px] leading-none font-semibold tracking-[-0.02em]">
          {meta.title}
        </h1>
        {/* The strapline is the first thing worth losing when the bar runs
         * out of room — the page title alone already says where you are. */}
        <p className="mt-1 hidden truncate text-[11.5px] leading-none text-[var(--fg-subtle)] sm:block">
          {meta.sub}
        </p>
      </div>

      <button
        onClick={() => setPaletteOpen(true)}
        className={cn(
          'group ml-auto hidden h-8 w-[min(360px,32vw)] items-center gap-2 rounded-[9px] border px-2.5 text-[12.5px] md:flex',
          'text-[var(--fg-subtle)] transition-colors duration-150 hover:border-[var(--line-strong)] hover:text-[var(--fg-muted)]',
        )}
        style={{ background: 'var(--surface-inset)', borderColor: 'var(--line)' }}
      >
        <Search size={14} className="shrink-0" />
        <span className="truncate">Search claims, tickets, districts…</span>
        <span className="ml-auto flex items-center gap-0.5">
          <Kbd>⌘</Kbd>
          <Kbd>K</Kbd>
        </span>
      </button>

      {/* Same palette, reduced to its icon. The full control needs ~360px it
       * cannot have next to a title and three status chips on a phone. */}
      <button
        onClick={() => setPaletteOpen(true)}
        aria-label="Search claims, tickets, districts"
        className="ml-auto grid size-8 shrink-0 place-items-center rounded-[8px] text-[var(--fg-muted)] transition-colors hover:bg-[var(--surface-3)] hover:text-[var(--fg)] md:hidden"
      >
        <Search size={16} />
      </button>

      <div className="flex shrink-0 items-center gap-2">
        {/* Status chips are context, not controls. They stand down on a
         * narrow bar so the menu, search and theme toggle stay reachable. */}
        {MOCK && (
          <Tooltip content="Mock mode — every number on screen comes from the bundled demo dataset, not a live source.">
            <span className="hidden sm:inline-flex">
              <Badge tone="violet">
                <FlaskConical size={11} />
                Mock data
              </Badge>
            </span>
          </Tooltip>
        )}

        {health?.data_down_mode && (
          <Tooltip content="Data-down mode: the weather source is treated as unreachable. Claims resolve to unverifiable and escalate — never to verified.">
            <span className="hidden sm:inline-flex">
              <Badge tone="warn">
                <AlertTriangle size={11} />
                Data-down
              </Badge>
            </span>
          </Tooltip>
        )}

        <Tooltip
          content={
            <div className="space-y-0.5">
              <div>WebSocket {wsLabel.toLowerCase()}</div>
              <div className="text-[var(--fg-subtle)]">
                Poller {health?.poller.running ? 'running' : 'stopped'} · last poll{' '}
                {ago(health?.poller.last_poll_at)}
              </div>
              {lastEventAt && (
                <div className="text-[var(--fg-subtle)]">Last event {ago(lastEventAt)}</div>
              )}
            </div>
          }
        >
          <span
            className="hidden h-7 items-center gap-2 rounded-full border px-2.5 text-[11.5px] font-medium sm:inline-flex"
            style={{
              background: 'var(--surface-inset)',
              borderColor: 'var(--line-strong)',
              color: 'var(--fg-muted)',
            }}
          >
            <LiveDot tone={wsTone} />
            {wsLabel}
          </span>
        </Tooltip>

        <IconButton label={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'} onClick={toggleTheme}>
          {theme === 'dark' ? <Sun size={15} /> : <Moon size={15} />}
        </IconButton>
      </div>
    </header>
  )
}
