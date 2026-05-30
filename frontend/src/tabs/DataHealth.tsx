import { useState } from 'react'
import { formatDistanceToNow } from 'date-fns'
import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  Database,
  RefreshCw,
  Wrench,
  XCircle,
} from 'lucide-react'
import { useDiagnostics } from '@/api/hooks'
import { KpiCard } from '@/components/common/KpiCard'
import { InfoTooltip } from '@/components/common/InfoTooltip'
import { SiteDetailDrawer } from '@/components/common/SiteDetailDrawer'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import type { DiagnosticsSite } from '@/types/api'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function statusColor(status: string): string {
  switch (status) {
    case 'Healthy':            return 'bg-success/10 text-success border-success/20'
    case 'OK':                 return 'bg-chart-3/10 text-chart-3 border-chart-3/20'
    case 'Sparse - BU fallback': return 'bg-warning/10 text-warning border-warning/20'
    case 'Low accuracy':       return 'bg-warning/10 text-warning border-warning/20'
    case 'No backtest':        return 'bg-muted text-muted-foreground border-border'
    case 'Insufficient data':  return 'bg-danger/10 text-danger border-danger/20'
    default:                   return 'bg-muted text-muted-foreground border-border'
  }
}

function stepDot(status: string | null | undefined) {
  if (status === 'ok') {
    return <span className="inline-block h-2.5 w-2.5 rounded-full bg-success" />
  }
  if (status === 'error') {
    return <span className="inline-block h-2.5 w-2.5 rounded-full bg-danger" />
  }
  return <span className="inline-block h-2.5 w-2.5 rounded-full bg-muted-foreground/40" />
}

function formatRelative(iso: string | null | undefined): string {
  if (!iso) return '—'
  try {
    return formatDistanceToNow(new Date(iso), { addSuffix: true })
  } catch {
    return iso
  }
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function PipelineBanner({
  lastRun,
  nextRunAt,
  latestData,
  latestPredicted,
  loading,
}: {
  lastRun: any
  nextRunAt: string | null
  latestData: string | null
  latestPredicted: string | null
  loading: boolean
}) {
  if (loading) {
    return <Skeleton className="h-32 w-full" />
  }

  const steps = lastRun?.steps ?? {}
  const stepNames = ['risk_scores', 'forecasters', 'backtest', 'drivers']

  return (
    <Card className="p-5">
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div>
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
            Last Pipeline Run
          </p>
          <p className="text-sm font-semibold text-foreground mt-1">
            {lastRun?.status ? lastRun.status.toUpperCase() : '—'}
          </p>
          <p className="text-xs text-muted-foreground">
            {formatRelative(lastRun?.finished_at)} ·{' '}
            {lastRun?.total_duration_s != null ? `${lastRun.total_duration_s}s` : '—'}
          </p>
          <p className="text-xs text-muted-foreground mt-0.5">trigger: {lastRun?.trigger ?? '—'}</p>
        </div>

        <div>
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
            Pipeline Steps
          </p>
          <div className="mt-2 space-y-1.5">
            {stepNames.map((name) => (
              <div key={name} className="flex items-center gap-2 text-xs text-foreground/80">
                {stepDot(steps[name]?.status)}
                <span className="font-medium">{name}</span>
                <span className="text-muted-foreground ml-auto tabular-nums">
                  {steps[name]?.duration_s != null ? `${steps[name].duration_s}s` : '—'}
                </span>
              </div>
            ))}
          </div>
        </div>

        <div>
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
            Next Scheduled Run
          </p>
          <p className="text-sm font-semibold text-foreground mt-1 flex items-center gap-1.5">
            <Clock className="h-4 w-4 text-muted-foreground" />
            {nextRunAt ? formatRelative(nextRunAt) : 'Not scheduled'}
          </p>
          <p className="text-xs text-muted-foreground mt-0.5">cron: nightly 02:00 UTC</p>
        </div>

        <div>
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
            Data Freshness
          </p>
          <p className="text-sm font-semibold text-foreground mt-1 flex items-center gap-1.5">
            <Database className="h-4 w-4 text-muted-foreground" />
            {latestData ?? '—'}
          </p>
          <p className="text-xs text-muted-foreground mt-0.5">
            latest predicted quarter: {latestPredicted ?? '—'}
          </p>
        </div>
      </div>
      {lastRun?.error_summary && (
        <div className="mt-4 p-3 bg-danger/10 border border-danger/20 rounded text-xs text-danger">
          <p className="font-semibold mb-1">Last run errors:</p>
          <p className="font-mono whitespace-pre-wrap">{lastRun.error_summary}</p>
        </div>
      )}
    </Card>
  )
}

function SiteHealthTable({
  sites,
  loading,
  query,
  filter,
  onSelectSite,
}: {
  sites: DiagnosticsSite[]
  loading: boolean
  query: string
  filter: string
  onSelectSite: (site: string) => void
}) {
  if (loading) {
    return (
      <Card>
        <CardContent className="p-5">
          <Skeleton className="h-6 w-full mb-3" />
          {Array.from({ length: 8 }).map((_, i) => (
            <Skeleton key={i} className="h-8 w-full mb-2" />
          ))}
        </CardContent>
      </Card>
    )
  }

  const q = query.trim().toLowerCase()
  const filtered = sites.filter((s) => {
    if (q && !s.site.toLowerCase().includes(q) && !(s.business_unit ?? '').toLowerCase().includes(q)) {
      return false
    }
    if (filter !== 'all' && s.status !== filter) {
      return false
    }
    return true
  })

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center justify-between">
          <span>Per-Site Data & Model Health</span>
          <span className="text-xs font-normal text-muted-foreground">
            {filtered.length} of {sites.length} sites
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent className="p-0 overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-xs uppercase tracking-wider text-muted-foreground">
              <th className="px-4 py-2.5 text-left">Site</th>
              <th className="px-4 py-2.5 text-left">BU</th>
              <th className="px-4 py-2.5 text-right">
                Incidents
                <InfoTooltip>Total incident rows attributed to this site in `ol_incidents`.</InfoTooltip>
              </th>
              <th className="px-4 py-2.5 text-right">
                Months
                <InfoTooltip>How many distinct (year, month) buckets this site has data in.</InfoTooltip>
              </th>
              <th className="px-4 py-2.5 text-left">
                Champion
                <InfoTooltip width="w-80">
                  The model picked for this site (lowest holdout error). Either
                  Prophet, XGBoost, an ensemble of the two, or `bu_prophet` when
                  the site is too sparse and we trained on its business unit.
                </InfoTooltip>
              </th>
              <th className="px-4 py-2.5 text-right">
                MAPE
                <InfoTooltip width="w-80">
                  <b>Mean Absolute Percentage Error</b> on the held-out quarters.
                  Smaller is better. 8% means the typical prediction was 8% away
                  from what actually happened.
                </InfoTooltip>
              </th>
              <th className="px-4 py-2.5 text-right">
                Accuracy (±20%)
                <InfoTooltip width="w-96">
                  % of held-out quarters where the prediction was within 20% of
                  the actual count. This is the headline accuracy number.
                  100% = the model nailed every test quarter; 50% = it was close
                  half the time. Click the row for the worked example.
                </InfoTooltip>
              </th>
              <th className="px-4 py-2.5 text-left">Status</th>
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 ? (
              <tr>
                <td colSpan={8} className="px-4 py-12 text-center text-muted-foreground">
                  No sites match the current filters.
                </td>
              </tr>
            ) : (
              filtered.map((s) => (
                <tr
                  key={s.site}
                  onClick={() => onSelectSite(s.site)}
                  className="border-b border-border/50 hover:bg-accent/40 cursor-pointer transition-colors"
                  title="Click for full details"
                >
                  <td className="px-4 py-2.5 font-medium text-foreground max-w-[180px]">
                    <span className="truncate block" title={s.site}>{s.site}</span>
                  </td>
                  <td className="px-4 py-2.5 text-muted-foreground text-xs max-w-[140px]">
                    <span className="truncate block" title={s.business_unit ?? ''}>
                      {s.business_unit ?? '—'}
                    </span>
                  </td>
                  <td className="px-4 py-2.5 text-right tabular-nums text-foreground">
                    {s.incidents.toLocaleString()}
                  </td>
                  <td className="px-4 py-2.5 text-right tabular-nums text-foreground">{s.n_months}</td>
                  <td className="px-4 py-2.5 text-xs text-foreground/80 capitalize">
                    {s.champion_model ?? '—'}
                  </td>
                  <td className="px-4 py-2.5 text-right tabular-nums text-xs text-foreground">
                    {s.holdout_mape != null ? `${s.holdout_mape}%` : '—'}
                  </td>
                  <td className="px-4 py-2.5 text-right tabular-nums text-xs text-foreground">
                    {s.backtest_pct_within_20 != null ? `${s.backtest_pct_within_20}%` : '—'}
                  </td>
                  <td className="px-4 py-2.5">
                    <span className={cn(
                      'inline-block text-xs px-2 py-0.5 rounded-full border whitespace-nowrap',
                      statusColor(s.status),
                    )}>
                      {s.status}
                    </span>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </CardContent>
    </Card>
  )
}

function AlertsPanel({
  siteVariants,
  categoryVariants,
  dataIssues,
  loading,
}: {
  siteVariants: any[]
  categoryVariants: any[]
  dataIssues: any
  loading: boolean
}) {
  if (loading) {
    return <Skeleton className="h-48 w-full" />
  }

  const issueChips = [
    { label: 'Null year',          count: dataIssues?.null_year ?? 0 },
    { label: 'Null month',         count: dataIssues?.null_month ?? 0 },
    { label: 'Null quarter',       count: dataIssues?.null_quarter ?? 0 },
    { label: 'Null severity',      count: dataIssues?.null_severity ?? 0 },
    { label: 'Invalid severity',   count: dataIssues?.invalid_severity ?? 0 },
    { label: 'Pre-2000 year',      count: dataIssues?.pre_2000_year ?? 0 },
  ]
  const hasAnyIssue = issueChips.some((c) => c.count > 0)

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
      {/* Data quality counts */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <AlertTriangle className="h-4 w-4 text-warning" />
            Data Quality Issues
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          <p className="text-xs text-muted-foreground">
            Total rows: <span className="font-semibold tabular-nums text-foreground">{dataIssues?.total_rows?.toLocaleString() ?? '—'}</span>
          </p>
          <div className="space-y-1.5">
            {issueChips.map((c) => (
              <div key={c.label} className="flex items-center justify-between text-xs">
                <span className="text-muted-foreground">{c.label}</span>
                <span className={cn(
                  'tabular-nums font-semibold px-2 py-0.5 rounded',
                  c.count > 0 ? 'bg-danger/10 text-danger' : 'bg-success/10 text-success',
                )}>
                  {c.count}
                </span>
              </div>
            ))}
          </div>
          {!hasAnyIssue && (
            <div className="flex items-center gap-1.5 text-xs text-success pt-2">
              <CheckCircle2 className="h-3.5 w-3.5" />
              No data quality issues detected.
            </div>
          )}
        </CardContent>
      </Card>

      {/* Site name variants */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Wrench className="h-4 w-4 text-warning" />
            Site Name Variants
          </CardTitle>
        </CardHeader>
        <CardContent>
          {siteVariants.length === 0 ? (
            <p className="text-xs text-muted-foreground italic">No duplicate site spellings detected.</p>
          ) : (
            <div className="space-y-2 max-h-64 overflow-y-auto">
              {siteVariants.map((v) => (
                <div key={v.canonical} className="text-xs">
                  <p className="font-semibold text-foreground">{v.canonical}</p>
                  <p className="text-muted-foreground text-[11px] mt-0.5 break-words">{v.variants}</p>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Category name variants */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Wrench className="h-4 w-4 text-warning" />
            Category Name Variants
          </CardTitle>
        </CardHeader>
        <CardContent>
          {categoryVariants.length === 0 ? (
            <p className="text-xs text-muted-foreground italic">No duplicate category spellings detected.</p>
          ) : (
            <div className="space-y-2 max-h-64 overflow-y-auto">
              {categoryVariants.map((v) => (
                <div key={v.canonical} className="text-xs">
                  <p className="font-semibold text-foreground">{v.canonical}</p>
                  <p className="text-muted-foreground text-[11px] mt-0.5 break-words">{v.variants}</p>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function DataHealth() {
  const diag = useDiagnostics()
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState('all')
  const [selectedSite, setSelectedSite] = useState<string | null>(null)

  const data = diag.data
  const loading = diag.isPending
  const summary = data?.summary
  const accuracy = data?.accuracy

  const statusFilters = [
    { value: 'all',                   label: 'All' },
    { value: 'Healthy',               label: 'Healthy' },
    { value: 'OK',                    label: 'OK' },
    { value: 'Sparse - BU fallback',  label: 'Sparse' },
    { value: 'Low accuracy',          label: 'Low accuracy' },
    { value: 'No backtest',           label: 'No backtest' },
    { value: 'Insufficient data',     label: 'Insufficient' },
  ]

  if (diag.isError) {
    return (
      <Card className="p-8">
        <div className="flex flex-col items-center gap-3 text-muted-foreground">
          <XCircle className="h-10 w-10 text-danger" />
          <p className="font-semibold">Failed to load diagnostics</p>
          <button
            onClick={() => diag.refetch()}
            className="text-sm text-primary hover:underline flex items-center gap-1"
          >
            <RefreshCw className="h-3.5 w-3.5" /> Retry
          </button>
        </div>
      </Card>
    )
  }

  return (
    <div className="space-y-6">
      {/* ── Page heading ─────────────────────────────────────────────── */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-bold text-foreground flex items-center gap-2">
            <Wrench className="h-5 w-5 text-muted-foreground" />
            Data & Model Health
          </h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            Pipeline status, per-site data quality, and source-data anomalies.
          </p>
        </div>
        <button
          onClick={() => diag.refetch()}
          className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1 border border-border rounded px-3 py-1.5 hover:bg-muted transition-colors"
        >
          <RefreshCw className={cn('h-3.5 w-3.5', diag.isFetching && 'animate-spin')} />
          Refresh
        </button>
      </div>

      {/* ── Pipeline banner ──────────────────────────────────────────── */}
      <PipelineBanner
        lastRun={data?.pipeline?.last_run}
        nextRunAt={data?.pipeline?.next_run_at ?? null}
        latestData={data?.freshness?.latest_data_date ?? null}
        latestPredicted={data?.freshness?.latest_predicted_quarter ?? null}
        loading={loading}
      />

      {/* ── Summary KPI row ─────────────────────────────────────────── */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        <KpiCard
          title="System Accuracy"
          value={
            accuracy?.weighted_pct_within_20 != null
              ? `${accuracy.weighted_pct_within_20.toFixed(0)}%`
              : '—'
          }
          subtitle={
            accuracy?.sites_evaluated != null
              ? `across ${accuracy.sites_evaluated} sites (±20%)`
              : 'within ±20%'
          }
          accentColor={
            accuracy?.weighted_pct_within_20 == null
              ? 'border-l-muted-foreground/40'
              : accuracy.weighted_pct_within_20 >= 75
              ? 'border-l-success'
              : accuracy.weighted_pct_within_20 >= 50
              ? 'border-l-chart-3'
              : 'border-l-warning'
          }
          loading={loading}
        />
        <KpiCard
          title="Total Sites"
          value={summary?.total_sites ?? 0}
          subtitle="in ol_incidents"
          loading={loading}
        />
        <KpiCard
          title="Healthy"
          value={summary?.healthy ?? 0}
          subtitle="accuracy ≥ 75%"
          accentColor="border-l-success"
          loading={loading}
        />
        <KpiCard
          title="Sparse / BU Fallback"
          value={summary?.sparse_bu_fallback ?? 0}
          subtitle="< 50 incidents or < 4 quarters"
          accentColor="border-l-warning"
          loading={loading}
        />
        <KpiCard
          title="Insufficient Data"
          value={summary?.insufficient_data ?? 0}
          subtitle="no champion model"
          accentColor="border-l-danger"
          loading={loading}
        />
      </div>

      {/* ── Filters ──────────────────────────────────────────────────── */}
      <Card className="p-3">
        <div className="flex flex-wrap items-center gap-3">
          <input
            type="text"
            placeholder="Search site or BU..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="border border-border bg-card text-foreground rounded px-3 py-1.5 text-sm w-64 focus:outline-none focus:ring-2 focus:ring-ring placeholder:text-muted-foreground"
          />
          <div className="flex flex-wrap gap-1.5">
            {statusFilters.map((f) => (
              <button
                key={f.value}
                onClick={() => setFilter(f.value)}
                className={cn(
                  'text-xs px-2.5 py-1 rounded-full border transition-colors',
                  filter === f.value
                    ? 'bg-primary text-primary-foreground border-primary'
                    : 'bg-card text-muted-foreground border-border hover:bg-muted',
                )}
              >
                {f.label}
              </button>
            ))}
          </div>
        </div>
      </Card>

      {/* ── Per-site table ──────────────────────────────────────────── */}
      <SiteHealthTable
        sites={data?.sites ?? []}
        loading={loading}
        query={query}
        filter={filter}
        onSelectSite={setSelectedSite}
      />

      {/* ── Alerts ───────────────────────────────────────────────────── */}
      <AlertsPanel
        siteVariants={data?.alerts?.site_variants ?? []}
        categoryVariants={data?.alerts?.category_variants ?? []}
        dataIssues={data?.alerts?.data_issues}
        loading={loading}
      />

      {/* ── Site detail drawer ──────────────────────────────────────── */}
      <SiteDetailDrawer
        site={selectedSite}
        onClose={() => setSelectedSite(null)}
      />
    </div>
  )
}
