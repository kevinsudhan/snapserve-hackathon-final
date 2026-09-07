import { useState } from 'react'
import { motion } from 'framer-motion'
import { MessageSquare } from 'lucide-react'
import type { CallRecord, Claim } from '@/types'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/base'
import { IntakeFacts } from './IntakeFacts'
import { WeatherCheck } from './WeatherCheck'
import { CropWindow, DisasterCards, EscalationCard, SchemeFacts } from './Sections'
import { RiskGauge } from './RiskGauge'
import { EvidencePanel } from './EvidencePanel'
import { TranscriptDrawer } from './Transcript'

const stagger = {
  hidden: {},
  show: { transition: { staggerChildren: 0.06 } },
}
const item = {
  hidden: { opacity: 0, y: 12 },
  show: { opacity: 1, y: 0, transition: { duration: 0.28, ease: [0.22, 1, 0.36, 1] as const } },
}

/**
 * The Truth Panel — the same component tree on the Live Desk and on a claim
 * page. Sections animate in as the ingest pipeline fills the claim.
 */
export function TruthPanel({
  claim,
  call,
  layout = 'stack',
  showTranscriptButton = true,
}: {
  claim: Claim
  call?: CallRecord
  layout?: 'stack' | 'grid'
  showTranscriptButton?: boolean
}) {
  const [transcriptOpen, setTranscriptOpen] = useState(false)

  return (
    <>
      <motion.div
        variants={stagger}
        initial="hidden"
        animate="show"
        className={cn(
          'space-y-4',
          layout === 'grid' && 'xl:grid xl:grid-cols-2 xl:items-start xl:gap-4 xl:space-y-0',
        )}
      >
        <motion.div variants={item} className={cn(layout === 'grid' && 'xl:col-span-2')}>
          <IntakeFacts claim={claim} />
        </motion.div>

        <motion.div variants={item} className={cn(layout === 'grid' && 'xl:col-span-2')}>
          <WeatherCheck claim={claim} />
        </motion.div>

        <motion.div variants={item} className={cn(layout === 'grid' && 'space-y-4 xl:space-y-4')}>
          <DisasterCards claim={claim} />
          {layout === 'grid' && <CropWindow claim={claim} />}
        </motion.div>

        {layout === 'stack' && (
          <motion.div variants={item}>
            <CropWindow claim={claim} />
          </motion.div>
        )}

        <motion.div variants={item}>
          <SchemeFacts claim={claim} />
        </motion.div>

        <motion.div variants={item} className={cn(layout === 'grid' && 'xl:col-span-2')}>
          <RiskGauge risk={claim.risk} />
        </motion.div>

        {(claim.escalation_reason || claim.farmer_explanation) && (
          <motion.div variants={item} className={cn(layout === 'grid' && 'xl:col-span-2')}>
            <EscalationCard claim={claim} />
          </motion.div>
        )}

        <motion.div variants={item} className={cn(layout === 'grid' && 'xl:col-span-2')}>
          <EvidencePanel claim={claim} />
        </motion.div>

        {showTranscriptButton && (
          <motion.div variants={item} className={cn('flex', layout === 'grid' && 'xl:col-span-2')}>
            <Button
              variant="outline"
              size="md"
              className="w-full"
              icon={<MessageSquare size={14} />}
              onClick={() => setTranscriptOpen(true)}
            >
              Open the transcript
              <span className="ml-1 text-[var(--fg-subtle)]">
                {call ? `· ${call.transcript.length} turns` : ''}
              </span>
            </Button>
          </motion.div>
        )}
      </motion.div>

      <TranscriptDrawer open={transcriptOpen} onOpenChange={setTranscriptOpen} call={call} />
    </>
  )
}
