import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/**
 * Fiscal quarter helpers — fiscal-year-START convention.
 *   Q1 = Apr-Jun, Q2 = Jul-Sep, Q3 = Oct-Dec, Q4 = Jan-Mar (wraps into next year)
 * Label format is `YYYY-Qn` where YYYY is the fiscal-year start year.
 */
const FISCAL_ORDER = ['Q1', 'Q2', 'Q3', 'Q4'] as const

/** (calendar year, month 1-12) → [fiscalYearStart, 'Qn'] */
function toFiscal(year: number, month: number): [number, string] {
  if (month >= 4 && month <= 6) return [year, 'Q1']
  if (month >= 7 && month <= 9) return [year, 'Q2']
  if (month >= 10) return [year, 'Q3']
  return [year - 1, 'Q4'] // Jan-Mar belongs to previous fiscal-year start
}

function currentFiscalQ(): [number, string] {
  const now = new Date()
  return toFiscal(now.getFullYear(), now.getMonth() + 1)
}

function prevFiscalQ(year: number, q: string): [number, string] {
  const idx = FISCAL_ORDER.indexOf(q as (typeof FISCAL_ORDER)[number])
  if (idx === 0) return [year - 1, 'Q4']
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

/** Theme-aware tint classes for a risk band (work in light + dark). */
export function riskColor(band: string | null | undefined): string {
  switch ((band ?? '').toLowerCase()) {
    case 'critical': return 'text-danger bg-danger/10'
    case 'high':     return 'text-warning bg-warning/10'
    case 'medium':   return 'text-warning bg-warning/10'
    default:         return 'text-success bg-success/10'
  }
}

/** Solid dot colours for scatter/heatmap marks (fixed hex, fine in both themes). */
export function riskDot(band: string | null | undefined): string {
  switch ((band ?? '').toLowerCase()) {
    case 'critical': return '#ef4444'
    case 'high':     return '#f97316'
    case 'medium':   return '#f59e0b'
    default:         return '#22c55e'
  }
}
