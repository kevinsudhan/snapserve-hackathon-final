import { useEffect } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { motion } from 'framer-motion'
import {
  BookOpenCheck,
  FileSearch,
  LayoutDashboard,
  PanelLeftClose,
  PanelLeftOpen,
  Radio,
  ShieldCheck,
  Ticket as TicketIcon,
  X,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { useUi } from '@/store/ui'
import { useLive } from '@/store/live'
import { LiveDot } from '@/components/ui/base'
import { Tooltip } from '@/components/ui/overlays'

const NAV = [
  { to: '/', label: 'Overview', icon: LayoutDashboard, end: true },
  { to: '/live', label: 'Live Desk', icon: Radio, live: true },
  { to: '/claims', label: 'Claims', icon: FileSearch },
  { to: '/tickets', label: 'Tickets', icon: TicketIcon },
  { to: '/knowledge', label: 'Knowledge', icon: BookOpenCheck },
  { to: '/guardrails', label: 'Guardrails', icon: ShieldCheck },
]

/**
 * The navigation rail, and the same rail as a drawer on a narrow screen.
 *
 * ------------------------------------------------------------------ *
 * WHY THIS BECAME TWO THINGS
 *
 * It was a rail and only a rail: 218px of fixed width in a flex row, at
 * every size. At 375px that left roughly 150px for the page, so the claim
 * detail rendered its reference broken over three lines and cut its own
 * right edge off. Nothing was responsive because nothing could be — the
 * rail took the space before the content was asked what it needed.
 *
 * Below `lg` the same element is taken out of the flow and slid in over
 * the page instead. One list, positioned two ways. A second copy of the
 * nav for mobile is a second place to add a link to, and the one that gets
 * forgotten is always the one you are not looking at.
 *
 * The collapse control is hidden in drawer mode: collapsing a panel that
 * is already overlaying the page has nothing to give back.
 * ------------------------------------------------------------------ */
export function Sidebar() {
  const collapsed = useUi((s) => s.railCollapsed)
  const toggleRail = useUi((s) => s.toggleRail)
  const navOpen = useUi((s) => s.navOpen)
  const setNavOpen = useUi((s) => s.setNavOpen)
  const activeCall = useLive((s) => s.activeCallId)
  const { pathname } = useLocation()

  // Picking a destination is the end of the drawer's job.
  useEffect(() => {
    setNavOpen(false)
  }, [pathname, setNavOpen])

  // Escape closes it, and the page underneath must not scroll while it is
  // covered. Both are undone on the way out so a wide viewport is untouched.
  useEffect(() => {
    if (!navOpen) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setNavOpen(false)
    }
    document.addEventListener('keydown', onKey)
    const previous = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = previous
    }
  }, [navOpen, setNavOpen])

  return (
    <>
      {/* The scrim. Tapping off the panel is the fastest way out of it. */}
      <div
        onClick={() => setNavOpen(false)}
        aria-hidden
        className={cn(
          // Above the sticky top bar, which is z-30. At the same level the
          // bar won as the later element in the DOM, leaving it looking
          // usable over a page that had been dimmed out from under it.
          'fixed inset-0 z-40 transition-opacity duration-200 lg:hidden',
          navOpen ? 'opacity-100' : 'pointer-events-none opacity-0',
        )}
        style={{ background: 'var(--overlay)', backdropFilter: 'blur(2px)' }}
      />

      <aside
        data-parked={!navOpen}
        className={cn(
          'drawer z-50 flex shrink-0 flex-col',
          // Drawer below lg, rail from lg up. Never both `fixed` and
          // `static` at one breakpoint — which of those wins depends on the
          // order the utilities happen to be emitted in, not on the order
          // they are written here.
          'fixed inset-y-0 left-0 lg:relative lg:inset-y-auto lg:z-20',
          navOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0',
        )}
        style={
          {
            '--rail-w': collapsed ? '62px' : '218px',
            background: 'linear-gradient(180deg, var(--surface-1), var(--bg))',
            borderRight: '1px solid var(--line)',
          } as React.CSSProperties
        }
      >
      <div
        className={cn(
          'flex h-14 items-center gap-2.5 px-4',
          collapsed && 'lg:justify-center lg:px-0',
        )}
      >
        <div
          className="grid size-7 shrink-0 place-items-center rounded-[8px] border"
          style={{
            background: 'linear-gradient(160deg, var(--accent-hi), var(--accent))',
            borderColor: 'var(--accent-line)',
            boxShadow: '0 4px 14px -6px var(--accent)',
          }}
        >
          <LeafMark />
        </div>
        <div className={cn('min-w-0', collapsed && 'lg:hidden')}>
          <div className="display truncate text-[14px] leading-none">Araxys Desk</div>
          <div className="mt-1 text-[10px] leading-none tracking-[0.08em] text-[var(--fg-label)] uppercase">
            Claims control
          </div>
        </div>

        {/* Only in drawer mode. On a rail there is nothing to close. */}
        <button
          onClick={() => setNavOpen(false)}
          aria-label="Close navigation"
          className="ml-auto grid size-8 shrink-0 place-items-center rounded-[8px] text-[var(--fg-muted)] transition-colors hover:bg-[var(--surface-3)] hover:text-[var(--fg)] lg:hidden"
        >
          <X size={16} />
        </button>
      </div>

      <div className="h-px" style={{ background: 'var(--line)' }} />

      <nav
        className={cn(
          'flex flex-1 flex-col gap-0.5 overflow-y-auto py-3',
          collapsed ? 'px-2.5 lg:px-2' : 'px-2.5',
        )}
      >
        {NAV.map((item) => {
          const Icon = item.icon
          const link = (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                cn(
                  'group relative flex h-9 items-center gap-2.5 rounded-[9px] px-2.5 text-[13px] font-medium transition-colors duration-150',
                  collapsed && 'lg:justify-center lg:px-0',
                  isActive
                    ? 'text-[var(--fg)]'
                    : 'text-[var(--fg-muted)] hover:bg-[var(--surface-3)] hover:text-[var(--fg)]',
                )
              }
            >
              {({ isActive }) => (
                <>
                  {isActive && (
                    <motion.span
                      layoutId="nav-active"
                      transition={{ type: 'spring', stiffness: 460, damping: 38 }}
                      className="absolute inset-0 rounded-[9px] border"
                      style={{
                        background: 'var(--surface-3)',
                        borderColor: 'var(--line-strong)',
                        boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.05)',
                      }}
                    />
                  )}
                  <span className="relative z-10 flex items-center gap-2.5">
                    <Icon size={16} strokeWidth={2} className={isActive ? 'text-[var(--accent-fg)]' : ''} />
                    <span className={cn('relative', collapsed && 'lg:hidden')}>{item.label}</span>
                  </span>
                  {item.live && activeCall != null && (
                    <span
                      className={cn(
                        'relative z-10 ml-auto',
                        collapsed && 'lg:absolute lg:top-1.5 lg:right-1.5 lg:ml-0',
                      )}
                    >
                      <LiveDot />
                    </span>
                  )}
                </>
              )}
            </NavLink>
          )
          // A collapsed rail shows icons with no words next to them, so it
          // needs the tooltip. The drawer always shows labels, and a tooltip
          // there would be repeating what is already on screen — harmless,
          // and it never fires on a touch pointer anyway.
          return collapsed ? (
            <Tooltip key={item.to} content={item.label} side="right">
              <div>{link}</div>
            </Tooltip>
          ) : (
            link
          )
        })}
      </nav>

      <div className={cn('hidden pb-3 lg:block', collapsed ? 'px-2' : 'px-2.5')}>
        <button
          onClick={toggleRail}
          className={cn(
            'flex h-8 w-full items-center gap-2.5 rounded-[9px] px-2.5 text-[12px] font-medium text-[var(--fg-muted)]',
            'transition-colors duration-150 hover:bg-[var(--surface-3)] hover:text-[var(--fg)]',
            collapsed && 'justify-center px-0',
          )}
          aria-label={collapsed ? 'Expand navigation' : 'Collapse navigation'}
        >
          {collapsed ? <PanelLeftOpen size={15} /> : <PanelLeftClose size={15} />}
          {!collapsed && 'Collapse'}
        </button>
      </div>
      </aside>
    </>
  )
}

function LeafMark() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M12 21c0-7 4.2-12 10-13.4C21.5 15.4 17.6 21 12 21Z"
        fill="var(--on-accent)"
        opacity="0.92"
      />
      <path d="M12 21c0-5.6-3.3-9.7-8-10.9C4.4 16.5 7.6 21 12 21Z" fill="var(--on-accent)" opacity="0.55" />
    </svg>
  )
}
