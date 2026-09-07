import * as React from 'react'
import { cn } from '@/lib/utils'

/* ------------------------------------------------------------------ *
 * Tones — every semantic colour is reachable through this one map so
 * chips, badges, rails and glows always agree with each other.
 * ------------------------------------------------------------------ */

export type Tone = 'accent' | 'ok' | 'warn' | 'danger' | 'sky' | 'violet' | 'teal' | 'neutral'

/**
 * Borders sit at 46% of the hue rather than 34%.
 *
 * A chip is a small tinted rectangle with small text in it. At 34% its
 * edge dissolved into the panel behind it and the chip stopped reading as
 * an object — which is most of why a screen full of status pills looked
 * washed rather than tagged. The fill stays low so the label keeps its
 * contrast; only the edge gets firmer.
 */
export const toneVars: Record<Tone, { fg: string; bg: string; line: string }> = {
  accent: { fg: 'var(--accent-fg)', bg: 'var(--accent-soft)', line: 'var(--accent-line)' },
  ok: { fg: 'var(--ok)', bg: 'var(--ok-soft)', line: 'color-mix(in srgb, var(--ok) 46%, transparent)' },
  warn: { fg: 'var(--warn)', bg: 'var(--warn-soft)', line: 'color-mix(in srgb, var(--warn) 46%, transparent)' },
  danger: { fg: 'var(--danger)', bg: 'var(--danger-soft)', line: 'color-mix(in srgb, var(--danger) 46%, transparent)' },
  sky: { fg: 'var(--sky)', bg: 'var(--sky-soft)', line: 'color-mix(in srgb, var(--sky) 46%, transparent)' },
  violet: { fg: 'var(--violet)', bg: 'var(--violet-soft)', line: 'color-mix(in srgb, var(--violet) 46%, transparent)' },
  teal: { fg: 'var(--teal)', bg: 'var(--teal-soft)', line: 'color-mix(in srgb, var(--teal) 46%, transparent)' },
  neutral: { fg: 'var(--fg-muted)', bg: 'var(--neutral-soft)', line: 'var(--line-strong)' },
}

/* ------------------------------------------------------------------ *
 * Panel
 * ------------------------------------------------------------------ */

export function Panel({
  className,
  flush,
  ...props
}: React.HTMLAttributes<HTMLDivElement> & { flush?: boolean }) {
  return <div className={cn(flush ? 'panel-flush' : 'panel', className)} {...props} />
}

export function PanelHeader({
  title,
  eyebrow,
  icon,
  tone = 'neutral',
  right,
  className,
}: {
  title: React.ReactNode
  eyebrow?: React.ReactNode
  icon?: React.ReactNode
  tone?: Tone
  right?: React.ReactNode
  className?: string
}) {
  const t = toneVars[tone]
  return (
    <div className={cn('flex items-start justify-between gap-4 px-5 pt-4 pb-3', className)}>
      <div className="flex min-w-0 items-center gap-3">
        {icon && (
          <span
            className="grid size-7 shrink-0 place-items-center rounded-[7px] border"
            style={{ color: t.fg, background: t.bg, borderColor: t.line }}
          >
            {icon}
          </span>
        )}
        <div className="min-w-0">
          {eyebrow && <div className="eyebrow mb-0.5">{eyebrow}</div>}
          <h3 className="truncate text-[15px] leading-tight font-semibold tracking-[-0.02em]">
            {title}
          </h3>
        </div>
      </div>
      {right && <div className="flex shrink-0 items-center gap-2">{right}</div>}
    </div>
  )
}

export function Divider({ className }: { className?: string }) {
  return <div className={cn('h-px w-full', className)} style={{ background: 'var(--line)' }} />
}

/* ------------------------------------------------------------------ *
 * Button
 * ------------------------------------------------------------------ */

type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'primary' | 'subtle' | 'ghost' | 'outline' | 'danger'
  size?: 'xs' | 'sm' | 'md'
  icon?: React.ReactNode
  trailing?: React.ReactNode
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { className, variant = 'subtle', size = 'sm', icon, trailing, children, ...props },
  ref,
) {
  return (
    <button
      ref={ref}
      className={cn(
        'group relative inline-flex items-center justify-center gap-1.5 rounded-[8px] font-medium whitespace-nowrap',
        'transition-[background,border-color,color,transform,box-shadow] duration-150 ease-out',
        'active:translate-y-px disabled:active:translate-y-0',
        // Opacity alone turned the accent gradient into pale mint, which
        // reads as a weak button rather than an unavailable one. Draining
        // most of the colour as well makes the state unmistakable, and
        // dropping the shadow sits it back down onto the surface.
        'disabled:opacity-55 disabled:grayscale-[0.75] disabled:shadow-none',
        size === 'xs' && 'h-6 px-2 text-[11px]',
        size === 'sm' && 'h-8 px-3 text-[13px]',
        size === 'md' && 'h-9.5 px-4 text-[13px]',
        variant === 'primary' &&
          'border shadow-[inset_0_1px_0_rgba(255,255,255,0.14)] text-[var(--on-accent)]',
        variant === 'subtle' && 'border text-[var(--fg)]',
        variant === 'outline' && 'border text-[var(--fg-muted)] hover:text-[var(--fg)]',
        variant === 'ghost' && 'text-[var(--fg-muted)] hover:text-[var(--fg)]',
        variant === 'danger' && 'border text-[var(--danger)]',
        className,
      )}
      style={{
        ...(variant === 'primary'
          ? {
              background: 'linear-gradient(180deg, var(--accent-hi) 0%, var(--accent) 100%)',
              borderColor: 'color-mix(in srgb, var(--accent) 72%, black)',
              boxShadow:
                'inset 0 1px 0 rgba(255,255,255,0.18), 0 1px 2px rgba(8,20,32,0.18), 0 6px 14px -8px var(--accent)',
            }
          : {}),
        ...(variant === 'subtle'
          ? { background: 'var(--surface-3)', borderColor: 'var(--line-strong)' }
          : {}),
        ...(variant === 'outline' ? { background: 'transparent', borderColor: 'var(--line-strong)' } : {}),
        ...(variant === 'ghost' ? { background: 'transparent' } : {}),
        ...(variant === 'danger'
          ? { background: 'var(--danger-soft)', borderColor: 'color-mix(in srgb, var(--danger) 32%, transparent)' }
          : {}),
        ...props.style,
      }}
      {...props}
    >
      {icon && <span className="shrink-0 opacity-90">{icon}</span>}
      {children}
      {trailing && <span className="shrink-0 opacity-70">{trailing}</span>}
    </button>
  )
})

export function IconButton({
  label,
  className,
  children,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { label: string }) {
  return (
    <button
      aria-label={label}
      title={label}
      className={cn(
        'grid size-8 place-items-center rounded-[8px] border border-transparent text-[var(--fg-muted)]',
        'transition-colors duration-150 hover:border-[var(--line-strong)] hover:bg-[var(--surface-3)] hover:text-[var(--fg)]',
        className,
      )}
      {...props}
    >
      {children}
    </button>
  )
}

/* ------------------------------------------------------------------ *
 * Badge / Chip
 * ------------------------------------------------------------------ */

export function Badge({
  tone = 'neutral',
  className,
  dot,
  children,
  mono,
  ...props
}: React.HTMLAttributes<HTMLSpanElement> & { tone?: Tone; dot?: boolean; mono?: boolean }) {
  const t = toneVars[tone]
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full border px-2 py-[3px] text-[11px] leading-none font-semibold',
        mono && 'mono',
        className,
      )}
      style={{ color: t.fg, background: t.bg, borderColor: t.line }}
      {...props}
    >
      {dot && <span className="size-1.5 rounded-full" style={{ background: t.fg }} />}
      {children}
    </span>
  )
}

export function Chip({
  className,
  active,
  children,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { active?: boolean }) {
  return (
    <button
      className={cn(
        'inline-flex h-7 items-center gap-1.5 rounded-full border px-3 text-[12px] font-medium transition-colors duration-150',
        active
          ? 'border-[var(--accent-line)] bg-[var(--accent-soft)] text-[var(--accent-fg)]'
          : 'border-[var(--line-strong)] bg-transparent text-[var(--fg-muted)] hover:bg-[var(--surface-3)] hover:text-[var(--fg)]',
        className,
      )}
      {...props}
    >
      {children}
    </button>
  )
}

export function Kbd({ children }: { children: React.ReactNode }) {
  return (
    <kbd
      className="mono inline-flex h-5 min-w-5 items-center justify-center rounded-[5px] border px-1.5 text-[10px] font-medium"
      style={{
        background: 'var(--surface-3)',
        borderColor: 'var(--line-strong)',
        color: 'var(--fg-muted)',
      }}
    >
      {children}
    </kbd>
  )
}

/* ------------------------------------------------------------------ *
 * Skeleton / empty / progress
 * ------------------------------------------------------------------ */

export function Skeleton({ className, style }: { className?: string; style?: React.CSSProperties }) {
  return <div className={cn('skeleton', className)} style={style} />
}

export function EmptyState({
  icon,
  title,
  hint,
  action,
  tone = 'neutral',
  className,
}: {
  icon?: React.ReactNode
  title: string
  hint?: string
  action?: React.ReactNode
  tone?: Tone
  className?: string
}) {
  const t = toneVars[tone]
  return (
    <div className={cn('flex flex-col items-center justify-center px-6 py-14 text-center', className)}>
      {icon && (
        <div
          className="mb-4 grid size-11 place-items-center rounded-[12px] border"
          style={{ color: t.fg, background: t.bg, borderColor: t.line }}
        >
          {icon}
        </div>
      )}
      <p className="text-[14px] font-semibold tracking-[-0.01em]">{title}</p>
      {hint && <p className="mt-1.5 max-w-sm text-[12.5px] text-[var(--fg-subtle)]">{hint}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  )
}

export function ProgressBar({
  value,
  tone = 'accent',
  className,
  height = 6,
}: {
  value: number
  tone?: Tone
  className?: string
  height?: number
}) {
  const t = toneVars[tone]
  return (
    <div
      className={cn('w-full overflow-hidden rounded-full', className)}
      style={{ height, background: 'var(--surface-inset)', border: '1px solid var(--line)' }}
    >
      <div
        className="h-full rounded-full transition-[width] duration-500 ease-out"
        style={{
          width: `${Math.max(0, Math.min(100, value * 100))}%`,
          background: `linear-gradient(90deg, color-mix(in srgb, ${t.fg} 55%, transparent), ${t.fg})`,
        }}
      />
    </div>
  )
}

/* ------------------------------------------------------------------ *
 * Live dot
 * ------------------------------------------------------------------ */

export function LiveDot({ tone = 'accent', size = 6 }: { tone?: Tone; size?: number }) {
  const t = toneVars[tone]
  return (
    <span className="relative inline-grid place-items-center" style={{ width: size, height: size }}>
      <span
        className="absolute inset-0 rounded-full"
        style={{ background: t.fg, animation: 'livepulse 1.9s ease-in-out infinite', opacity: 0.5 }}
      />
      <span className="relative rounded-full" style={{ width: size, height: size, background: t.fg }} />
    </span>
  )
}

/* ------------------------------------------------------------------ *
 * Field — a label/value pair used across the truth panel
 * ------------------------------------------------------------------ */

export function Field({
  label,
  value,
  hint,
  mono,
  className,
}: {
  label: string
  value: React.ReactNode
  hint?: React.ReactNode
  mono?: boolean
  className?: string
}) {
  return (
    <div className={cn('min-w-0', className)}>
      <div className="eyebrow mb-1">{label}</div>
      <div className={cn('truncate text-[13.5px] font-medium', mono && 'mono')}>{value}</div>
      {hint && <div className="mt-0.5 truncate text-[11.5px] text-[var(--fg-subtle)]">{hint}</div>}
    </div>
  )
}
