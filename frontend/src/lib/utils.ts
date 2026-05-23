import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/** Fiscal quarter helpers — Q4=Jan-Mar, Q1=Apr-Jun, Q2=Jul-Sep, Q3=Oct-Dec */
const FISCAL_ORDER = ['Q4', 'Q1', 'Q2', 'Q3'] as const

function currentFiscalQ(): [number, string] {
  const now = new Date()
  const m = now.getMonth() + 1
  const q = m >= 10 ? 'Q3' : m >= 7 ? 'Q2' : m >= 4 ? 'Q1' : 'Q4'
  return [now.getFullYear(), q]
}

function prevFiscalQ(year: number, q: string): [number, string] {
  const idx = FISCAL_ORDER.indexOf(q as (typeof FISCAL_ORDER)[number])
  if (idx === 0) return [year - 1, 'Q3']
  return [year, FISCAL_ORDER[idx - 1]]
}

export function generateQuarterOptions(n = 12): string[] {
  let [year, q] = currentFiscalQ()
  const options: string[] = []
  for (let i = 0; i < n; i++) {
    options.push(`${year}-${q}`)
    ;[year, q] = prevFiscalQ(year, q)
  }
  return options
}

/** Returns the most recent COMPLETE quarter (one behind current) */
export function defaultQuarter(): string {
  const [year, q] = currentFiscalQ()
  const [py, pq] = prevFiscalQ(year, q)
  return `${py}-${pq}`
}

export function formatDelta(val: number | null | undefined): string {
  if (val == null) return '—'
  const sign = val > 0 ? '+' : ''
  return `${sign}${val.toFixed(1)}%`
}

export function riskColor(band: string | null | undefined): string {
  switch ((band ?? '').toLowerCase()) {
    case 'critical': return 'text-red-600 bg-red-50'
    case 'high':     return 'text-orange-600 bg-orange-50'
    case 'medium':   return 'text-amber-600 bg-amber-50'
    default:         return 'text-green-600 bg-green-50'
  }
}

export function riskDot(band: string | null | undefined): string {
  switch ((band ?? '').toLowerCase()) {
    case 'critical': return '#ef4444'
    case 'high':     return '#f97316'
    case 'medium':   return '#f59e0b'
    default:         return '#22c55e'
  }
}
