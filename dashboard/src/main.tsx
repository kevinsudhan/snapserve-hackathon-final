import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import App from './App'
import { bootTheme } from './store/ui'
import './styles/index.css'

bootTheme()

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 10_000,
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
})

/**
 * No <StrictMode>: framer-motion 12's AnimatePresence leaks exiting nodes under
 * React 18's double-invoked effects, which left ghost cards on the Live Desk and
 * the ticket board. Everything here is effect-clean either way.
 */
createRoot(document.getElementById('root')!).render(
  <QueryClientProvider client={queryClient}>
    <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <App />
    </BrowserRouter>
  </QueryClientProvider>,
)
