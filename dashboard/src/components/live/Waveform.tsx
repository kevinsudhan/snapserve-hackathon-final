import { useMemo } from 'react'
import { motion, useReducedMotion } from 'framer-motion'

/**
 * Decorative voice-activity bars for the in-progress call card.
 * Purely indicative — SnapServe holds the audio, we never receive it.
 */
export function Waveform({
  bars = 34,
  active = true,
  height = 42,
  color = 'var(--accent-hi)',
}: {
  bars?: number
  active?: boolean
  height?: number
  color?: string
}) {
  const reduced = useReducedMotion()
  const seeds = useMemo(
    () => Array.from({ length: bars }, (_, i) => 0.28 + Math.abs(Math.sin(i * 1.7) * 0.62)),
    [bars],
  )

  return (
    <div
      className="flex items-end gap-[3px]"
      style={{ height }}
      role="img"
      aria-label={active ? 'Call in progress' : 'Call ended'}
    >
      {seeds.map((s, i) => {
        const base = height * (active ? s : 0.12)
        return (
          <motion.span
            key={i}
            className="w-[3px] shrink-0 rounded-full"
            style={{
              background: active ? color : 'var(--line-strong)',
              opacity: active ? 0.35 + s * 0.55 : 0.5,
            }}
            initial={{ height: base * 0.4 }}
            animate={
              reduced || !active
                ? { height: base }
                : { height: [base * 0.35, base, base * 0.55, base * 0.9, base * 0.4] }
            }
            transition={
              reduced || !active
                ? { duration: 0.25 }
                : {
                    duration: 1.05 + (i % 5) * 0.16,
                    repeat: Infinity,
                    repeatType: 'mirror',
                    ease: 'easeInOut',
                    delay: (i % 7) * 0.05,
                  }
            }
          />
        )
      })}
    </div>
  )
}
