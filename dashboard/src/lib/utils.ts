import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'
import { format, formatDistanceToNowStrict, parseISO } from 'date-fns'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export const MOCK = import.meta.env.VITE_MOCK === '1'

export const DEMO_PHONE = '+91 79658 54267'

/* ---------- dates ---------- */

export function safeDate(value?: string | null): Date | null {
  if (!value) return null
  try {
    const d = value.includes('T') ? parseISO(value) : new Date(`${value}T00:00:00`)
    return Number.isNaN(d.getTime()) ? null : d
  } catch {
    return null
  }
}

export function fmtDate(value?: string | null, pattern = 'd MMM yyyy') {
  const d = safeDate(value)
  return d ? format(d, pattern) : '—'
}

export function fmtTime(value?: string | null) {
  const d = safeDate(value)
  return d ? format(d, 'HH:mm:ss') : '—'
}

export function fmtDateTime(value?: string | null) {
  const d = safeDate(value)
  return d ? format(d, 'd MMM, HH:mm') : '—'
}

export function ago(value?: string | null) {
  const d = safeDate(value)
  if (!d) return '—'
  return `${formatDistanceToNowStrict(d)} ago`
}

export function shortDay(value?: string | null) {
  const d = safeDate(value)
  return d ? format(d, 'd MMM') : '—'
}

export function duration(seconds?: number | null) {
  if (seconds == null) return '—'
  const s = Math.max(0, Math.round(seconds))
  const m = Math.floor(s / 60)
  return `${String(m).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`
}

/* ---------- numbers ---------- */

export function nf(value: number, digits = 0) {
  return value.toLocaleString('en-IN', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })
}

export function mm(value?: number | null) {
  return value == null ? '—' : `${nf(value, 1)} mm`
}

export function kmh(value?: number | null) {
  return value == null ? '—' : `${nf(value, 0)} km/h`
}

export function pct(value: number) {
  return `${Math.round(value * 100)}%`
}

/* ---------- language ---------- */

const LANGUAGE_NAMES: Record<string, string> = {
  ta: 'Tamil',
  hi: 'Hindi',
  te: 'Telugu',
  kn: 'Kannada',
  ml: 'Malayalam',
  mr: 'Marathi',
  bn: 'Bengali',
  gu: 'Gujarati',
  pa: 'Punjabi',
  or: 'Odia',
  as: 'Assamese',
  ur: 'Urdu',
  en: 'English',
}

export function languageName(code?: string | null) {
  if (!code) return 'Unknown'
  const base = code.split('-')[0].toLowerCase()
  return LANGUAGE_NAMES[base] ?? code.toUpperCase()
}

/* ---------- labels ---------- */

export function titleize(value?: string | null) {
  if (!value) return '—'
  return value
    .replace(/[_-]+/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase())
}

export function initials(value?: string | null) {
  if (!value) return '··'
  return value
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? '')
    .join('')
}

/* ---------- misc ---------- */

export async function copyText(text: string) {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    return false
  }
}

export function sleep(ms: number) {
  return new Promise((r) => setTimeout(r, ms))
}

export function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value))
}
