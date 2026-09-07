import * as React from 'react'
import * as RDialog from '@radix-ui/react-dialog'
import * as RTooltip from '@radix-ui/react-tooltip'
import * as RPopover from '@radix-ui/react-popover'
import { X } from 'lucide-react'
import { cn } from '@/lib/utils'
import { IconButton } from './base'

export function TooltipProvider({ children }: { children: React.ReactNode }) {
  return (
    <RTooltip.Provider delayDuration={180} skipDelayDuration={300}>
      {children}
    </RTooltip.Provider>
  )
}

export function Tooltip({
  children,
  content,
  side = 'top',
  align = 'center',
}: {
  children: React.ReactNode
  content: React.ReactNode
  side?: 'top' | 'bottom' | 'left' | 'right'
  align?: 'start' | 'center' | 'end'
}) {
  if (!content) return <>{children}</>
  return (
    <RTooltip.Root>
      <RTooltip.Trigger asChild>{children}</RTooltip.Trigger>
      <RTooltip.Portal>
        <RTooltip.Content
          side={side}
          align={align}
          sideOffset={7}
          className="z-[70] max-w-[280px] rounded-[8px] border px-2.5 py-1.5 text-[12px] leading-snug data-[state=delayed-open]:animate-[fadeIn_140ms_ease-out]"
          style={{
            background: 'var(--surface-3)',
            borderColor: 'var(--line-strong)',
            color: 'var(--fg)',
            boxShadow: 'var(--pop-shadow)',
          }}
        >
          {content}
        </RTooltip.Content>
      </RTooltip.Portal>
    </RTooltip.Root>
  )
}

const overlayClass =
  'fixed inset-0 z-[60] backdrop-blur-[3px] data-[state=open]:animate-[fadeIn_180ms_ease-out] data-[state=closed]:animate-[fadeOut_140ms_ease-in]'

export function Modal({
  open,
  onOpenChange,
  title,
  description,
  children,
  footer,
  size = 'md',
}: {
  open: boolean
  onOpenChange: (v: boolean) => void
  title: React.ReactNode
  description?: React.ReactNode
  children: React.ReactNode
  footer?: React.ReactNode
  size?: 'sm' | 'md' | 'lg'
}) {
  return (
    <RDialog.Root open={open} onOpenChange={onOpenChange}>
      <RDialog.Portal>
        <RDialog.Overlay className={overlayClass} style={{ background: 'var(--overlay)' }} />
        <RDialog.Content
          className={cn(
            'fixed top-1/2 left-1/2 z-[65] w-[calc(100vw-2rem)] -translate-x-1/2 -translate-y-1/2 overflow-hidden rounded-[14px] border',
            'data-[state=open]:animate-[popIn_200ms_cubic-bezier(0.22,1,0.36,1)]',
            size === 'sm' && 'max-w-[400px]',
            size === 'md' && 'max-w-[560px]',
            size === 'lg' && 'max-w-[860px]',
          )}
          style={{
            background: 'var(--surface-1)',
            borderColor: 'var(--line-strong)',
            boxShadow: 'var(--pop-shadow)',
          }}
        >
          <div className="flex items-start justify-between gap-4 px-5 pt-4 pb-3">
            <div className="min-w-0">
              <RDialog.Title className="text-[15px] font-semibold tracking-[-0.02em]">
                {title}
              </RDialog.Title>
              {description && (
                <RDialog.Description className="mt-1 text-[12.5px] text-[var(--fg-subtle)]">
                  {description}
                </RDialog.Description>
              )}
            </div>
            <RDialog.Close asChild>
              <IconButton label="Close" className="-mt-1 -mr-1">
                <X size={15} />
              </IconButton>
            </RDialog.Close>
          </div>
          <div className="h-px w-full" style={{ background: 'var(--line)' }} />
          <div className="max-h-[70vh] overflow-y-auto px-5 py-4">{children}</div>
          {footer && (
            <>
              <div className="h-px w-full" style={{ background: 'var(--line)' }} />
              <div className="flex items-center justify-end gap-2 px-5 py-3">{footer}</div>
            </>
          )}
        </RDialog.Content>
      </RDialog.Portal>
    </RDialog.Root>
  )
}

export function Drawer({
  open,
  onOpenChange,
  title,
  description,
  children,
  width = 560,
  side = 'right',
}: {
  open: boolean
  onOpenChange: (v: boolean) => void
  title: React.ReactNode
  description?: React.ReactNode
  children: React.ReactNode
  width?: number
  side?: 'right' | 'bottom'
}) {
  return (
    <RDialog.Root open={open} onOpenChange={onOpenChange}>
      <RDialog.Portal>
        <RDialog.Overlay className={overlayClass} style={{ background: 'var(--overlay)' }} />
        <RDialog.Content
          className={cn(
            'fixed z-[65] flex flex-col border',
            side === 'right'
              ? 'top-0 right-0 bottom-0 w-[calc(100vw-2rem)] rounded-l-[14px] data-[state=open]:animate-[slideInRight_240ms_cubic-bezier(0.22,1,0.36,1)]'
              : 'right-0 bottom-0 left-0 max-h-[86vh] rounded-t-[16px] data-[state=open]:animate-[slideInUp_240ms_cubic-bezier(0.22,1,0.36,1)]',
          )}
          style={{
            background: 'var(--surface-1)',
            borderColor: 'var(--line-strong)',
            boxShadow: 'var(--pop-shadow)',
            ...(side === 'right' ? { maxWidth: width } : {}),
          }}
        >
          <div className="flex items-start justify-between gap-4 px-5 pt-4 pb-3">
            <div className="min-w-0">
              <RDialog.Title className="text-[15px] font-semibold tracking-[-0.02em]">
                {title}
              </RDialog.Title>
              {description && (
                <RDialog.Description className="mt-1 text-[12.5px] text-[var(--fg-subtle)]">
                  {description}
                </RDialog.Description>
              )}
            </div>
            <RDialog.Close asChild>
              <IconButton label="Close" className="-mt-1 -mr-1">
                <X size={15} />
              </IconButton>
            </RDialog.Close>
          </div>
          <div className="h-px w-full" style={{ background: 'var(--line)' }} />
          <div className="min-h-0 flex-1 overflow-y-auto">{children}</div>
        </RDialog.Content>
      </RDialog.Portal>
    </RDialog.Root>
  )
}

export function Popover({
  trigger,
  children,
  align = 'start',
  side = 'top',
  width = 340,
}: {
  trigger: React.ReactNode
  children: React.ReactNode
  align?: 'start' | 'center' | 'end'
  side?: 'top' | 'bottom' | 'left' | 'right'
  width?: number
}) {
  return (
    <RPopover.Root>
      <RPopover.Trigger asChild>{trigger}</RPopover.Trigger>
      <RPopover.Portal>
        <RPopover.Content
          align={align}
          side={side}
          sideOffset={8}
          collisionPadding={16}
          className="z-[70] rounded-[11px] border p-3.5 data-[state=open]:animate-[riseIn_170ms_cubic-bezier(0.22,1,0.36,1)]"
          style={{
            width,
            background: 'var(--surface-2)',
            borderColor: 'var(--line-strong)',
            boxShadow: 'var(--pop-shadow)',
          }}
        >
          {children}
          <RPopover.Arrow style={{ fill: 'var(--surface-2)' }} />
        </RPopover.Content>
      </RPopover.Portal>
    </RPopover.Root>
  )
}
