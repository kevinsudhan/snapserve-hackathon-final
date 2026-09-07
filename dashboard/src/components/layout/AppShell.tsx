import { Suspense } from 'react'
import { Outlet, useLocation } from 'react-router-dom'
import { AnimatePresence, motion } from 'framer-motion'
import { Sidebar } from './Sidebar'
import { TopBar } from './TopBar'
import { CommandPalette } from './CommandPalette'
import { Skeleton } from '@/components/ui/base'

export function AppShell() {
  const { pathname } = useLocation()
  return (
    <div className="room-light flex h-dvh w-full overflow-hidden">
      <Sidebar />
      <div className="relative flex min-w-0 flex-1 flex-col">
        <div className="grid-veil pointer-events-none absolute inset-0 opacity-70" aria-hidden />
        <TopBar />
        <main className="relative min-h-0 flex-1 overflow-y-auto">
          <AnimatePresence mode="wait">
            <motion.div
              key={pathname.split('/').slice(0, 2).join('/')}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -4 }}
              transition={{ duration: 0.2, ease: [0.22, 1, 0.36, 1] }}
              className="mx-auto w-full max-w-[1560px] px-3.5 py-4 sm:px-5 sm:py-5 xl:px-7"
            >
              <Suspense fallback={<RouteFallback />}>
                <Outlet />
              </Suspense>
            </motion.div>
          </AnimatePresence>
        </main>
      </div>
      <CommandPalette />
    </div>
  )
}

function RouteFallback() {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-[104px] rounded-[13px]" />
        ))}
      </div>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Skeleton className="h-[320px] rounded-[13px]" />
        <Skeleton className="h-[320px] rounded-[13px]" />
        <Skeleton className="h-[320px] rounded-[13px]" />
      </div>
    </div>
  )
}
