import { Link } from 'react-router-dom'
import { Compass } from 'lucide-react'
import { EmptyState, Panel } from '@/components/ui/base'

export default function NotFound() {
  return (
    <Panel>
      <EmptyState
        icon={<Compass size={18} />}
        title="No page at that address"
        hint="Press ⌘K to jump to the Live Desk, a claim, or the knowledge snapshot."
        action={
          <Link to="/" className="text-[13px] font-medium text-[var(--accent-fg)] hover:underline">
            Back to the overview
          </Link>
        }
        className="py-24"
      />
    </Panel>
  )
}
