import type { ReactNode } from 'react'
import {
  ComposedChart, Area, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer, ReferenceLine,
} from 'recharts'
import { formatDistanceToNow } from 'date-fns'
import { Activity, Brain, Target, Zap } from 'lucide-react'
import { useFilters } from '@/context/FilterContext'
import { usePredictions, useIncidentTrend, useBacktest } from '@/api/hooks'
import { ChartCard } from '@/components/common/ChartCard'
import { SeverityBadge } from '@/components/common/SeverityBadge'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { useChartTheme } from '@/lib/useChartTheme'
import { cn } from '@/lib/utils'
import type { TrendPoint, BacktestPoint, PredictionItem } from '@/types/api'

// ---------------------------------------------------------------------------
// Confidence badge colours
// ---------------------------------------------------------------------------

function confidenceBorderColor(band: string | null | undefined) {
  switch ((band ?? '').toLowerCase()) {
    case 'high':   return 'border-l-success'
    case 'medium': return 'border-l-warning'
    default:       return 'border-l-danger'
  }
}

// ---------------------------------------------------------------------------
// Chart data assembly
// ---------------------------------------------------------------------------

interface ChartPoint {
  label: string
  actual: number | null
  backtest: number | null
  forecast: number | null
  lower: number | null
  upper_diff: number | null
  isToday?: boolean
}

// Backtest rows are labelled by fiscal quarter (e.g. "2026-Q4"), but the
// historic chart points are keyed by month ("2026-01").  Convert a quarter
// label to its FIRST calendar month so the keys align.
// Fiscal convention (lib/quarters.py): Q1=Apr, Q2=Jul, Q3=Oct, Q4=Jan.
function quarterToFirstMonthKey(quarter: string): string {
  const [year, q] = quarter.split('-')
  const startMonth: Record<string, string> = { Q1: '04', Q2: '07', Q3: '10', Q4: '01' }
  return `${year}-${startMonth[q] ?? '01'}`
}

function buildChartData(
  trend: TrendPoint[],
  backtest: BacktestPoint[],
  predictions: PredictionItem[],
): ChartPoint[] {
  const btMap = new Map(backtest.map((b) => [quarterToFirstMonthKey(b.month), b.predicted]))

  // Last 12 months of actuals
  const historic: ChartPoint[] = trend.slice(-12).map((t) => {
    const monthKey = `${t.year}-${String(t.month).padStart(2, '0')}`
    return {
      label: t.month_label,
      actual: t.count,
      backtest: btMap.has(monthKey) ? (btMap.get(monthKey) ?? null) : null,
      forecast: null,
      lower: null,
      upper_diff: null,
    }
  })

  // Today marker on the last historical point
  if (historic.length > 0) {
    historic[historic.length - 1].isToday = true
  }

  // Next 3 quarterly forecasts
  const forecast: ChartPoint[] = predictions.map((p) => ({
    label: p.target_quarter,
    actual: null,
    backtest: null,
    forecast: p.predicted_count,
    lower: p.lower_ci,
    upper_diff:
      p.upper_ci != null && p.lower_ci != null ? p.upper_ci - p.lower_ci : null,
  }))

  return [...historic, ...forecast]
}

// ---------------------------------------------------------------------------
// Accuracy stat
// ---------------------------------------------------------------------------

function calcAccuracy(backtest: BacktestPoint[]): { pct: number; threshold: number } | null {
  const threshold = 20
  const valid = backtest.filter((b) => b.actual != null && b.actual > 0 && b.predicted != null)
  if (valid.length === 0) return null
  const within = valid.filter(
    (b) => Math.abs((b.actual! - b.predicted!) / b.actual!) * 100 <= threshold,
  )
  return { pct: Math.round((within.length / valid.length) * 100), threshold }
}

// ---------------------------------------------------------------------------
// Model Info strip
// ---------------------------------------------------------------------------

function MetaCard({
  icon,
  label,
  value,
  loading,
}: {
  icon: ReactNode
  label: string
  value: string | number | null | undefined
  loading?: boolean
}) {
  return (
    <Card className="p-4 flex items-center gap-3 card-hover">
      <div className="shrink-0 h-8 w-8 rounded-lg bg-primary/10 flex items-center justify-center text-primary">
        {icon}
      </div>
      <div className="min-w-0">
        <p className="text-xs text-muted-foreground uppercase tracking-wider font-medium">{label}</p>
        {loading ? (
          <Skeleton className="h-5 w-20 mt-1" />
        ) : (
          <p className="text-sm font-semibold text-foreground truncate">{value ?? '—'}</p>
        )}
      </div>
    </Card>
  )
}

// ---------------------------------------------------------------------------
// Custom tooltip for the chart
// ---------------------------------------------------------------------------

function ChartTooltip({ active, payload, label }: {
  active?: boolean
  payload?: Array<{ name: string; value: number | null; color: string }>
  label?: string
}) {
  if (!active || !payload?.length) return null
  return (
    <div className="bg-popover border border-border rounded-lg shadow-lg p-3 text-xs space-y-1 min-w-[140px] text-popover-foreground">
      <p className="font-semibold">{label}</p>
      {payload.map((entry) =>
        entry.value != null ? (
          <div key={entry.name} className="flex justify-between gap-4">
            <span style={{ color: entry.color }}>{entry.name}</span>
            <span className="font-medium">{Math.round(entry.value)}</span>
          </div>
        ) : null,
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function Predictions() {
  const { selectedSite } = useFilters()
  const predQ    = usePredictions(selectedSite)
  const trendQ   = useIncidentTrend(selectedSite, 12)
  const backtestQ = useBacktest(selectedSite)
  const ct = useChartTheme()

  const response  = predQ.data
  const meta      = response?.model_meta
  const preds     = response?.predictions ?? []
  const trend     = trendQ.data ?? []
  const backtest  = backtestQ.data ?? []

  const chartData = buildChartData(trend, backtest, preds)
  const accuracy  = calcAccuracy(backtest)

  const lastTrainedStr = meta?.last_trained_at
    ? formatDistanceToNow(new Date(meta.last_trained_at), { addSuffix: true })
    : null

  const isLoading = predQ.isPending

  return (
    <div className="space-y-6">

      {/* ── Model Info strip ─────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <MetaCard
          icon={<Brain className="h-4 w-4" />}
          label="Champion Model"
          value={meta?.champion_model ? meta.champion_model.charAt(0).toUpperCase() + meta.champion_model.slice(1) : null}
          loading={isLoading}
        />
        <MetaCard
          icon={<Target className="h-4 w-4" />}
          label="Holdout RMSE"
          value={meta?.holdout_rmse != null ? meta.holdout_rmse.toFixed(2) : null}
          loading={isLoading}
        />
        <MetaCard
          icon={<Activity className="h-4 w-4" />}
          label="Holdout MAPE"
          value={meta?.holdout_mape != null ? `${meta.holdout_mape.toFixed(1)}%` : null}
          loading={isLoading}
        />
        <MetaCard
          icon={<Zap className="h-4 w-4" />}
          label="Last Trained"
          value={lastTrainedStr}
          loading={isLoading}
        />
      </div>

      {/* ── Main forecast chart ──────────────────────────────────────────── */}
      <ChartCard
        title="Incident Forecast"
        subtitle="Actuals (12 months) · Backtest overlay (dashed orange) · Forecast with 80% CI"
        loading={isLoading || trendQ.isPending || backtestQ.isPending}
        error={predQ.isError}
        onRetry={() => predQ.refetch()}
        height={320}
        headerRight={preds[0]?.confidence_band && (
          <SeverityBadge band={preds[0].confidence_band} />
        )}
      >
        <ResponsiveContainer width="100%" height={320}>
          <ComposedChart data={chartData} margin={{ top: 10, right: 30, bottom: 0, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={ct.grid} />
            <XAxis dataKey="label" tick={{ fontSize: 10, fill: ct.axis }} tickLine={false} />
            <YAxis tick={{ fontSize: 10, fill: ct.axis }} tickLine={false} axisLine={false} />
            <Tooltip content={<ChartTooltip />} />
            <Legend iconSize={8} wrapperStyle={{ fontSize: 11 }} />

            {/* CI band: transparent base + coloured diff */}
            <Area dataKey="lower" stackId="ci" fill="transparent" stroke="none" legendType="none" name="CI lower" />
            <Area dataKey="upper_diff" stackId="ci" fill={ct.warning} fillOpacity={0.18} stroke="none" name="80% CI" />

            {/* Actual historical */}
            <Line type="monotone" dataKey="actual" stroke={ct.primary} strokeWidth={2} dot={{ r: 3, fill: ct.primary }} connectNulls={false} name="Actual" />

            {/* Backtest (model in-sample) */}
            <Line type="monotone" dataKey="backtest" stroke={ct.warning} strokeWidth={1.8} strokeDasharray="5 3" dot={false} connectNulls={false} name="Backtest" />

            {/* Forecast */}
            <Line type="monotone" dataKey="forecast" stroke={ct.warning} strokeWidth={2.5} dot={{ r: 5, fill: ct.warning, stroke: ct.tooltipBg, strokeWidth: 2 }} connectNulls={false} name="Forecast" />

            {/* Today reference line */}
            {chartData.find((d) => d.isToday) && (
              <ReferenceLine
                x={chartData.find((d) => d.isToday)?.label}
                stroke={ct.axis}
                strokeDasharray="4 4"
                label={{ value: 'Today', position: 'top', fontSize: 10, fill: ct.axis }}
              />
            )}
          </ComposedChart>
        </ResponsiveContainer>
      </ChartCard>

      {/* ── Accuracy at a Glance ─────────────────────────────────────────── */}
      {accuracy && (
        <Card className="px-5 py-4 flex items-center gap-4">
          <div className={cn(
            'h-12 w-12 rounded-full flex items-center justify-center text-sm font-bold shrink-0',
            accuracy.pct >= 75 ? 'bg-success/15 text-success' :
            accuracy.pct >= 50 ? 'bg-warning/15 text-warning' :
                                  'bg-danger/15 text-danger',
          )}>
            {accuracy.pct}%
          </div>
          <div>
            <p className="text-sm font-semibold text-foreground">Accuracy at a Glance</p>
            <p className="text-xs text-muted-foreground mt-0.5">
              Model predicted within ±{accuracy.threshold}% of actual in{' '}
              <span className="font-medium">{accuracy.pct}%</span> of recent quarters
              {backtest.length > 0 && ` (${backtest.length}-quarter backtest)`}
            </p>
          </div>
        </Card>
      )}

      {/* ── Per-quarter detail cards ──────────────────────────────────────── */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {isLoading
          ? Array.from({ length: 3 }).map((_, i) => (
              <Card key={i} className="p-5 space-y-3">
                <Skeleton className="h-3 w-24" />
                <Skeleton className="h-8 w-16" />
                <Skeleton className="h-3 w-32" />
              </Card>
            ))
          : preds.map((p) => {
              const displayRange =
                p.lower_ci != null && p.upper_ci != null
                  ? `${Math.round(p.lower_ci)} – ${Math.round(p.upper_ci)}`
                  : null

              return (
                <Card
                  key={p.id}
                  className={cn('p-5 border-l-4 card-hover', confidenceBorderColor(p.confidence_band))}
                >
                  <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                    {p.target_quarter}
                  </p>
                  <p className="text-3xl font-bold text-foreground mt-1 tabular-nums">
                    {p.predicted_count != null ? Math.round(p.predicted_count) : '—'}
                  </p>
                  {displayRange && (
                    <p className="text-xs text-muted-foreground mt-1 tabular-nums">
                      Range: {displayRange}
                    </p>
                  )}
                  <div className="mt-2 flex items-center gap-2">
                    <SeverityBadge band={p.confidence_band} size="sm" />
                    <span className="text-xs text-muted-foreground capitalize">{p.model_name}</span>
                  </div>
                </Card>
              )
            })}
      </div>
    </div>
  )
}
