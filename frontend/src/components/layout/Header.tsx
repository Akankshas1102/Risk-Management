import { Building2, Calendar, RefreshCw } from 'lucide-react'
import { useFilters } from '@/context/FilterContext'
import { useSites } from '@/api/hooks'
import { generateQuarterOptions } from '@/lib/utils'

const QUARTERS = generateQuarterOptions(12)

const QUARTER_LABELS: Record<string, string> = {
  Q4: 'Jan–Mar',
  Q1: 'Apr–Jun',
  Q2: 'Jul–Sep',
  Q3: 'Oct–Dec',
}

function quarterLabel(q: string): string {
  const [year, qn] = q.split('-')
  return `${q}  (${QUARTER_LABELS[qn] ?? ''} ${year})`
}

interface HeaderProps {
  sidebarWidth: number
}

export function Header({ sidebarWidth }: HeaderProps) {
  const { selectedSite, setSelectedSite, selectedQuarter, setSelectedQuarter } = useFilters()
  const sitesQuery = useSites(selectedQuarter)

  const selectBase =
    'h-9 rounded-lg border border-slate-200 bg-white px-3 pr-8 text-sm text-slate-700 shadow-sm focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-brand-500 appearance-none cursor-pointer hover:border-slate-300'

  return (
    <header
      className="fixed top-0 right-0 z-30 flex h-16 items-center gap-4 border-b border-slate-200 bg-white px-6 shadow-sm transition-all duration-200"
      style={{ left: sidebarWidth }}
    >
      {/* Site selector */}
      <div className="relative flex items-center gap-2">
        <Building2 className="h-4 w-4 text-slate-400 shrink-0" />
        <div className="relative">
          <select
            value={selectedSite}
            onChange={(e) => setSelectedSite(e.target.value)}
            className={selectBase}
            style={{ minWidth: 180 }}
            aria-label="Select site"
          >
            {sitesQuery.isPending && <option>Loading sites…</option>}
            {(sitesQuery.data ?? []).map((s) => (
              <option key={s.site} value={s.site}>
                {s.site}
              </option>
            ))}
          </select>
          <span className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 text-xs">▾</span>
        </div>
      </div>

      {/* Quarter selector */}
      <div className="relative flex items-center gap-2">
        <Calendar className="h-4 w-4 text-slate-400 shrink-0" />
        <div className="relative">
          <select
            value={selectedQuarter}
            onChange={(e) => setSelectedQuarter(e.target.value)}
            className={selectBase}
            style={{ minWidth: 220 }}
            aria-label="Select quarter"
          >
            {QUARTERS.map((q) => (
              <option key={q} value={q}>
                {quarterLabel(q)}
              </option>
            ))}
          </select>
          <span className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 text-xs">▾</span>
        </div>
      </div>

      <div className="flex-1" />

      {sitesQuery.isFetching && (
        <RefreshCw className="h-4 w-4 text-slate-400 animate-spin" />
      )}
    </header>
  )
}
