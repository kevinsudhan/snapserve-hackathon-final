import { lazy, useEffect } from 'react'
import { Route, Routes } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { Toaster } from 'sonner'
import { AppShell } from '@/components/layout/AppShell'
import { TooltipProvider } from '@/components/ui/overlays'
import { connectLive, disconnectLive } from '@/lib/ws'
import { useUi } from '@/store/ui'

const Overview = lazy(() => import('@/pages/Overview'))
const LiveDesk = lazy(() => import('@/pages/LiveDesk'))
const Claims = lazy(() => import('@/pages/Claims'))
const ClaimDetail = lazy(() => import('@/pages/ClaimDetail'))
const Tickets = lazy(() => import('@/pages/Tickets'))
const Knowledge = lazy(() => import('@/pages/Knowledge'))
const Guardrails = lazy(() => import('@/pages/Guardrails'))
const EvidencePage = lazy(() => import('@/pages/Evidence'))
const NotFound = lazy(() => import('@/pages/NotFound'))

export default function App() {
  const qc = useQueryClient()
  const theme = useUi((s) => s.theme)

  useEffect(() => {
    connectLive(qc)
    return () => disconnectLive()
  }, [qc])

  return (
    <TooltipProvider>
      <Routes>
        {/* public, chrome-free, mobile-first evidence upload page */}
        <Route path="/e/:token" element={<EvidencePage />} />

        <Route element={<AppShell />}>
          <Route path="/" element={<Overview />} />
          <Route path="/live" element={<LiveDesk />} />
          <Route path="/claims" element={<Claims />} />
          <Route path="/claims/:id" element={<ClaimDetail />} />
          <Route path="/tickets" element={<Tickets />} />
          <Route path="/knowledge" element={<Knowledge />} />
          <Route path="/guardrails" element={<Guardrails />} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>

      <Toaster
        position="bottom-right"
        theme={theme}
        toastOptions={{
          style: {
            background: 'var(--surface-2)',
            border: '1px solid var(--line-strong)',
            color: 'var(--fg)',
            boxShadow: 'var(--pop-shadow)',
            borderRadius: '11px',
            fontSize: '13px',
          },
        }}
      />
    </TooltipProvider>
  )
}
