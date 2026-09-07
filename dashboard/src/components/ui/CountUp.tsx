import { useEffect, useRef, useState } from 'react'
import { useReducedMotion } from 'framer-motion'
import { cn } from '@/lib/utils'

/** Animated number that counts to `value`; static when reduced motion is on. */
export function CountUp({
  value,
  duration = 900,
  decimals = 0,
  suffix,
  className,
}: {
  value: number
  duration?: number
  decimals?: number
  suffix?: string
  className?: string
}) {
  const reduced = useReducedMotion()
  const [display, setDisplay] = useState(reduced ? value : 0)
  const from = useRef(0)
  const raf = useRef<number>(0)

  useEffect(() => {
    if (reduced) {
      setDisplay(value)
      return
    }
    const start = performance.now()
    const origin = from.current
    const delta = value - origin

    const tick = (t: number) => {
      const p = Math.min(1, (t - start) / duration)
      const eased = 1 - (1 - p) ** 3
      setDisplay(origin + delta * eased)
      if (p < 1) raf.current = requestAnimationFrame(tick)
      else from.current = value
    }
    raf.current = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf.current)
  }, [value, duration, reduced])

  return (
    <span className={cn('num', className)}>
      {display.toLocaleString('en-IN', {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals,
      })}
      {suffix}
    </span>
  )
}
