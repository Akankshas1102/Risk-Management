import { X } from 'lucide-react'
import { formatDistanceToNow } from 'date-fns'
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis,
  CartesianGrid, Tooltip, Cell,
} from 'recharts'
import { useSiteDetail } from '@/api/hooks'
import { Skeleton } from '@/components/ui/skeleton'
import { InfoTooltip } from '@/components/common/InfoTooltip'
import { useChartTheme } from '@/lib/useChartTheme'
import { cn } from '@/lib/utils'
import type { SiteDetailResponse } from '@/types/api'

const STATUS_COLORS: Record<string, string> = {
  'Healthy':                'bg-success/10 text-success border-success/20',
  'OK':                     'bg-chart-3/10 text-chart-3 border-chart-3/20',
  'Sparse - BU fallback':   'bg-warning/10 text-warning border-warning/20',
  'Low accuracy':           'bg-warning/10 text-warning border-warning/20',
  'No backtest':            'bg-muted text-muted-foreground border-border',
  'Insufficient data':      'bg-danger/10 text-danger border-danger/20',
}

function fmt(n: number | null | undefined, digits = 0): string {
  if (n == null) return '—'
  return n.toFixed(digits)
}

/** Pull "Oct-Dec 2025" out of "2025-Q3 (Oct-Dec 2025)". */
function calendarMonths(label: string): string {
  const m = label.match(/\(([^)]+)\)/)
  return m ? m[1] : ''
}

interface Props {
  site: string | null
  onClose: () => void
}

export function SiteDetailDrawer({ site, onClose }: Props) {
  const detail = useSiteDetail(site ?? undefined)

  if (!site) return null

  const open = !!site
  const data = detail.data

  return (
    <>
      {/* Backdrop */}
      <div
        className={cn(
          'fixed inset-0 bg-black/50 z-40 transition-opacity backdrop-blur-sm',
          open ? 'opacity-100' : 'opacity-0 pointer-events-none',
        )}
        onClick={onClose}
      />

      {/* Drawer panel */}
      <div
        className={cn(
          'fixed top-0 right-0 h-full w-full md:w-[720px] bg-background text-foreground',
          'shadow-2xl z-50 transition-transform duration-200 overflow-y-auto',
          open ? 'translate-x-0' : 'translate-x-full',
        )}
      >
        {/* Sticky header */}
        <div className="sticky top-0 bg-card/90 backdrop-blur border-b border-border px-6 py-4 flex items-start justify-between z-10">
          <div className="min-w-0">
            <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
              Site Detail
            </p>
            <h2 className="text-lg font-bold text-foreground truncate">{site}</h2>
            {data?.business_unit && (
              <p className="text-xs text-muted-foreground truncate">BU: {data.business_unit}</p>
            )}
          </div>
          <button
            onClick={onClose}
            className="text-muted-foreground hover:text-foreground p-1 rounded-lg hover:bg-muted transition-colors"
            aria-label="Close"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="p-6 space-y-6">
          {detail.isPending && <Skeleton className="h-96 w-full" />}
          {detail.isError && (
            <div className="text-sm text-danger">
              Failed to load detail for {site}.
            </div>
          )}
          {data && <DrawerBody data={data} />}
        </div>
      </div>
    </>
  )
}


function DrawerBody({ data }: { data: SiteDetailResponse }) {
  const t = data.totals
  const ct = useChartTheme()
  const lastTrained = data.model.last_trained_at
    ? formatDistanceToNow(new Date(data.model.last_trained_at), { addSuffix: true })
    : null

  const trainSet = new Set(data.training.train_quarters)
  const holdoutSet = new Set(data.training.holdout_quarters)
  const series = data.quarterly_series.map((q) => ({
    quarter: q.quarter,
    months: calendarMonths(q.label),
    incidents: q.incidents,
    phase: trainSet.has(q.quarter) ? 'train' : holdoutSet.has(q.quarter) ? 'holdout' : 'other',
  }))

  const holdoutCalendar = data.training.holdout_quarters
    .map((q) => {
      const point = data.quarterly_series.find((p) => p.quarter === q)
      return point ? calendarMonths(point.label) : q
    })
    .join('  →  ')

  return (
    <>
      {/* 1. STATUS */}
      <section className="bg-card rounded-lg border border-border p-4">
        <div className="flex items-center gap-3 flex-wrap">
          <span className={cn(
            'text-xs px-2 py-0.5 rounded-full border font-medium',
            STATUS_COLORS[data.status] ?? 'bg-muted text-muted-foreground',
          )}>
            {data.status}
          </span>
          {data.model.champion_model && (
            <span className="text-xs text-muted-foreground">
              Champion model: <span className="font-semibold capitalize text-foreground">{data.model.champion_model}</span>
            </span>
          )}
          {lastTrained && <span className="text-xs text-muted-foreground">Trained {lastTrained}</span>}
        </div>
        <p className="text-sm text-foreground/90 mt-3 leading-relaxed">{data.reason}</p>
        <p className="text-[11px] text-muted-foreground mt-2 leading-relaxed">
          <b>Fiscal-quarter labels:</b> Q1 = Apr-Jun · Q2 = Jul-Sep · Q3 = Oct-Dec ·
          Q4 = Jan-Mar (wraps into the next calendar year).
        </p>
      </section>

      {/* 2. DATA SUMMARY */}
      <section>
        <h3 className="text-sm font-semibold text-foreground mb-2">Data this site has</h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <Stat label="Total incidents" value={t.incidents.toLocaleString()} />
          <Stat label="Distinct months" value={t.distinct_months} />
          <Stat label="Distinct quarters" value={t.distinct_quarters} />
          <Stat label="First / last" value={
            t.first_incident && t.last_incident
              ? `${t.first_incident.slice(0, 7)} → ${t.last_incident.slice(0, 7)}`
              : '—'
          } />
        </div>
      </section>

      {/* 3. PER YEAR */}
      <section className="bg-card rounded-lg border border-border p-4">
        <h3 className="text-sm font-semibold text-foreground mb-3">
          Incidents per year
          <InfoTooltip>How many incidents occurred at this site each calendar year.</InfoTooltip>
        </h3>
        {data.per_year.length === 0 ? (
          <p className="text-xs text-muted-foreground">No yearly data.</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-xs uppercase tracking-wider text-muted-foreground">
                <th className="text-left py-1.5">Year</th>
                <th className="text-right py-1.5">Incidents</th>
              </tr>
            </thead>
            <tbody>
              {data.per_year.map((y) => (
                <tr key={y.year} className="border-b border-border/50">
                  <td className="py-1.5 text-foreground/90">{y.year}</td>
                  <td className="py-1.5 text-right tabular-nums text-foreground">{y.incidents.toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      {/* 4. TRAIN vs HOLDOUT CHART */}
      {series.length > 0 && (
        <section className="bg-card rounded-lg border border-border p-4">
          <h3 className="text-sm font-semibold text-foreground mb-1">
            Quarterly time series
            <InfoTooltip width="w-80">
              Grey bars are every fiscal quarter with data. <span className="text-chart-1 font-semibold">Blue</span> bars
              trained the model; <span className="text-warning font-semibold">orange</span> bars were held out to test it.
              Fiscal labels: Q1=Apr-Jun, Q2=Jul-Sep, Q3=Oct-Dec, Q4=Jan-Mar.
            </InfoTooltip>
          </h3>
          <div className="flex items-center gap-4 mb-1 text-xs text-muted-foreground flex-wrap">
            <LegendDot color={ct.palette[0]} label={`Train (${data.training.train_quarters.length} qtrs)`} />
            <LegendDot color={ct.warning} label={`Holdout (${data.training.holdout_quarters.length} qtrs)`} />
            <LegendDot color={ct.grid} label="Other" />
          </div>
          {holdoutCalendar && (
            <p className="text-xs text-muted-foreground mb-2">
              Holdout window in calendar months:{' '}
              <span className="font-semibold text-foreground">{holdoutCalendar}</span>
            </p>
          )}
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={series} margin={{ top: 8, right: 8, bottom: 24, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={ct.grid} />
              <XAxis
                dataKey="quarter"
                tick={(props) => {
                  const { x, y, payload } = props
                  const point = series.find((s) => s.quarter === payload.value)
                  return (
                    <g transform={`translate(${x},${y})`}>
                      <text dy={12} textAnchor="middle" fontSize={10} fill={ct.axis}>{payload.value}</text>
                      {point?.months && (
                        <text dy={26} textAnchor="middle" fontSize={9} fill={ct.axis} opacity={0.7}>{point.months}</text>
                      )}
                    </g>
                  )
                }}
              />
              <YAxis tick={{ fontSize: 10, fill: ct.axis }} />
              <Tooltip
                cursor={{ fill: ct.grid, fillOpacity: 0.3 }}
                content={({ active, payload }) => {
                  if (!active || !payload?.length) return null
                  const p = payload[0].payload as typeof series[0]
                  return (
                    <div className="bg-popover border border-border rounded-lg shadow-lg p-2 text-xs text-popover-foreground">
                      <p className="font-semibold">{p.quarter}</p>
                      {p.months && <p className="text-muted-foreground">{p.months}</p>}
                      <p>Incidents: <span className="tabular-nums font-semibold">{p.incidents}</span></p>
                      <p className="text-muted-foreground capitalize">Phase: {p.phase}</p>
                    </div>
                  )
                }}
              />
              <Bar dataKey="incidents">
                {series.map((s, i) => (
                  <Cell key={i} fill={s.phase === 'train' ? ct.palette[0] : s.phase === 'holdout' ? ct.warning : ct.grid} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </section>
      )}

      {/* 5. ACCURACY */}
      <section className="bg-card rounded-lg border border-border p-4">
        <div className="flex items-baseline justify-between gap-2 mb-3">
          <h3 className="text-sm font-semibold text-foreground">
            Accuracy
            <InfoTooltip width="w-96">
              We hide the last few quarters from the model and ask it to predict them.
              Each row shows the guess vs reality, plus the percentage difference.
              "<b>Within ±20%</b>" counts how often the guess was that close — the headline accuracy.
            </InfoTooltip>
          </h3>
          {data.backtest.pct_within_20 != null && (
            <div className="text-right">
              <div className={cn(
                'text-2xl font-bold tabular-nums',
                data.backtest.pct_within_20 >= 75 ? 'text-success' :
                data.backtest.pct_within_20 >= 50 ? 'text-chart-3' : 'text-danger',
              )}>
                {fmt(data.backtest.pct_within_20, 0)}%
              </div>
              <p className="text-xs text-muted-foreground">within ±20%</p>
            </div>
          )}
        </div>

        {data.backtest.rows.length === 0 ? (
          <p className="text-xs text-muted-foreground">No backtest results stored for this site.</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-xs uppercase tracking-wider text-muted-foreground">
                <th className="text-left py-1.5">Quarter</th>
                <th className="text-right py-1.5">Actual</th>
                <th className="text-right py-1.5">Predicted</th>
                <th className="text-right py-1.5">Error %</th>
                <th className="text-center py-1.5">±20%</th>
              </tr>
            </thead>
            <tbody>
              {data.backtest.rows.map((r) => (
                <tr key={r.quarter} className="border-b border-border/50">
                  <td className="py-1.5 text-foreground/90 text-xs">{r.label}</td>
                  <td className="py-1.5 text-right tabular-nums text-foreground">{fmt(r.actual)}</td>
                  <td className="py-1.5 text-right tabular-nums text-foreground">{fmt(r.predicted)}</td>
                  <td className="py-1.5 text-right tabular-nums text-foreground">{fmt(r.abs_pct_error, 1)}%</td>
                  <td className="py-1.5 text-center">{r.within_20 ? '✅' : '❌'}</td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr className="text-xs text-muted-foreground">
                <td className="py-2">Mean error</td>
                <td colSpan={2}></td>
                <td className="text-right tabular-nums">{fmt(data.backtest.mean_ape, 1)}%</td>
                <td></td>
              </tr>
            </tfoot>
          </table>
        )}

        <div className="grid grid-cols-3 gap-2 mt-4 text-xs">
          <MiniStat label="RMSE" value={fmt(data.model.holdout_rmse, 2)}
            tooltip="Root Mean Squared Error in incident counts. Smaller = better. RMSE=12 means typical miss is ~12 incidents." />
          <MiniStat label="MAPE" value={data.model.holdout_mape != null ? `${fmt(data.model.holdout_mape, 1)}%` : '—'}
            tooltip="Mean Absolute Percentage Error on the holdout. Smaller = better." />
          <MiniStat label="Within ±30%" value={data.backtest.pct_within_30 != null ? `${fmt(data.backtest.pct_within_30, 0)}%` : '—'}
            tooltip="Looser tolerance — % of holdout quarters within 30% of actual." />
        </div>
      </section>

      {/* 6. FORECAST */}
      <section className="bg-card rounded-lg border border-border p-4">
        <h3 className="text-sm font-semibold text-foreground mb-3">
          Forecast for the next quarters
          <InfoTooltip width="w-80">
            What the model expects for the next 3 fiscal quarters. The CI range is the
            80% confidence band — the model thinks the real value lands inside it 8 times out of 10.
          </InfoTooltip>
        </h3>
        {data.forecast.length === 0 ? (
          <p className="text-xs text-muted-foreground">No forecast available.</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-xs uppercase tracking-wider text-muted-foreground">
                <th className="text-left py-1.5">Target quarter</th>
                <th className="text-right py-1.5">Predicted</th>
                <th className="text-right py-1.5">Range (80% CI)</th>
                <th className="text-left py-1.5">Confidence</th>
              </tr>
            </thead>
            <tbody>
              {data.forecast.map((f) => (
                <tr key={f.quarter} className="border-b border-border/50">
                  <td className="py-1.5 text-foreground/90 text-xs">{f.label}</td>
                  <td className="py-1.5 text-right tabular-nums font-semibold text-foreground">
                    {f.predicted != null ? Math.round(f.predicted) : '—'}
                  </td>
                  <td className="py-1.5 text-right tabular-nums text-xs text-muted-foreground">
                    {f.lower_ci != null && f.upper_ci != null
                      ? `${Math.round(f.lower_ci)} – ${Math.round(f.upper_ci)}`
                      : '—'}
                  </td>
                  <td className="py-1.5 text-xs capitalize text-foreground/80">{f.confidence_band ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {data.forecast[0]?.training_data_through && (
          <p className="text-xs text-muted-foreground mt-2">
            Training data through {data.forecast[0].training_data_through}.
          </p>
        )}
      </section>
    </>
  )
}

// ---------------------------------------------------------------------------
// Small helpers
// ---------------------------------------------------------------------------

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="bg-card rounded-lg border border-border p-3">
      <p className="text-xs text-muted-foreground uppercase tracking-wider">{label}</p>
      <p className="text-base font-semibold text-foreground mt-0.5 truncate" title={String(value)}>
        {value}
      </p>
    </div>
  )
}

function MiniStat({ label, value, tooltip }: { label: string; value: string; tooltip?: string }) {
  return (
    <div className="bg-muted rounded p-2 text-center">
      <p className="text-[10px] text-muted-foreground uppercase tracking-wider flex items-center justify-center">
        {label}
        {tooltip && <InfoTooltip>{tooltip}</InfoTooltip>}
      </p>
      <p className="text-sm font-semibold text-foreground tabular-nums mt-0.5">{value}</p>
    </div>
  )
}

function LegendDot({ color, label }: { color: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="inline-block w-3 h-3 rounded" style={{ backgroundColor: color }} />
      {label}
    </span>
  )
}
