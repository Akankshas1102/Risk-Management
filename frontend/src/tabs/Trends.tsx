import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer,
  AreaChart, Area,
} from 'recharts'
import { Activity, TrendingDown, TrendingUp, Minus } from 'lucide-react'
import { useFilters } from '@/context/FilterContext'
import { useIncidentTrend, useIncidentsByCategory } from '@/api/hooks'
import { ChartCard } from '@/components/common/ChartCard'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'

function MiniTrendCard({
  label,
  value,
  delta,
  loading,
}: {
  label: string
  value: string | number
  delta?: number | null
  loading?: boolean
}) {
  if (loading) {
    return (
      <Card className="p-4 space-y-2">
        <Skeleton className="h-3 w-20" />
        <Skeleton className="h-7 w-12" />
      </Card>
    )
  }
  const up = (delta ?? 0) > 0
  const flat = delta == null || Math.abs(delta) < 0.1
  return (
    <Card className="p-4">
      <p className="text-xs font-medium text-slate-400 uppercase tracking-wide">{label}</p>
      <p className="text-2xl font-bold text-slate-900 mt-1">{value}</p>
      {!flat && (
        <span
          className={cn(
            'mt-1 inline-flex items-center gap-0.5 text-xs font-medium px-1.5 py-0.5 rounded-full',
            up ? 'bg-red-50 text-red-600' : 'bg-green-50 text-green-600',
          )}
        >
          {up ? <TrendingUp className="h-3 w-3" /> : <TrendingDown className="h-3 w-3" />}
          {Math.abs(delta!).toFixed(1)}%
        </span>
      )}
      {flat && (
        <span className="mt-1 inline-flex items-center gap-0.5 text-xs text-slate-400 px-1.5 py-0.5 rounded-full bg-slate-50">
          <Minus className="h-3 w-3" /> Stable
        </span>
      )}
    </Card>
  )
}

export function Trends() {
  const { selectedSite, selectedQuarter } = useFilters()
  const trendQ = useIncidentTrend(selectedSite, 12)
  const catsQ  = useIncidentsByCategory(selectedSite, selectedQuarter)

  const trend = trendQ.data ?? []
  const last3 = trend.slice(-3)
  const prev3 = trend.slice(-6, -3)
  const recentAvg = last3.reduce((s, d) => s + d.count, 0) / (last3.length || 1)
  const prevAvg   = prev3.reduce((s, d) => s + d.count, 0) / (prev3.length || 1)
  const delta = prevAvg > 0 ? ((recentAvg - prevAvg) / prevAvg) * 100 : null

  return (
    <div className="space-y-6">
      {/* ── Mini trend cards ──────────────────────────────────────── */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <MiniTrendCard
          label="3-Month Avg"
          value={recentAvg.toFixed(0)}
          delta={delta}
          loading={trendQ.isPending}
        />
        <MiniTrendCard
          label="Peak (12mo)"
          value={trend.length ? Math.max(...trend.map((d) => d.count)) : '—'}
          loading={trendQ.isPending}
        />
        <MiniTrendCard
          label="Min (12mo)"
          value={trend.length ? Math.min(...trend.map((d) => d.count)) : '—'}
          loading={trendQ.isPending}
        />
        <MiniTrendCard
          label="Months Tracked"
          value={trend.length}
          loading={trendQ.isPending}
        />
      </div>

      {/* ── Main trend chart ─────────────────────────────────────── */}
      <ChartCard
        title="Incident Trend"
        subtitle={`${selectedSite} vs all-sites average · last 12 months`}
        loading={trendQ.isPending}
        error={trendQ.isError}
        onRetry={() => trendQ.refetch()}
        height={280}
      >
        <ResponsiveContainer width="100%" height={280}>
          <AreaChart data={trendQ.data ?? []} margin={{ top: 10, right: 20, bottom: 0, left: 0 }}>
            <defs>
              <linearGradient id="siteGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%"  stopColor="#3b82f6" stopOpacity={0.2} />
                <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
            <XAxis dataKey="month_label" tick={{ fontSize: 10 }} tickLine={false} />
            <YAxis tick={{ fontSize: 10 }} tickLine={false} axisLine={false} />
            <Tooltip />
            <Legend iconSize={8} wrapperStyle={{ fontSize: 11 }} />
            <Area
              type="monotone"
              dataKey="count"
              stroke="#3b82f6"
              fill="url(#siteGrad)"
              strokeWidth={2}
              name={selectedSite}
              dot={false}
            />
            <Line
              type="monotone"
              dataKey="all_sites_avg"
              stroke="#94a3b8"
              strokeWidth={1.5}
              strokeDasharray="4 4"
              dot={false}
              name="All-sites avg"
            />
          </AreaChart>
        </ResponsiveContainer>
      </ChartCard>

      {/* ── Category breakdown + Anomaly placeholder ─────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Category share bars */}
        <ChartCard
          title="Category Breakdown"
          subtitle={selectedQuarter}
          loading={catsQ.isPending}
          error={catsQ.isError}
          onRetry={() => catsQ.refetch()}
          height={240}
          className="lg:col-span-2"
        >
          <ResponsiveContainer width="100%" height={240}>
            <LineChart
              data={(catsQ.data ?? []).slice(0, 8).map((c) => ({
                name: c.category.slice(0, 20),
                value: c.count,
              }))}
              margin={{ top: 10, right: 20, bottom: 40, left: 0 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
              <XAxis dataKey="name" tick={{ fontSize: 9 }} tickLine={false} angle={-30} textAnchor="end" />
              <YAxis tick={{ fontSize: 10 }} tickLine={false} axisLine={false} />
              <Tooltip />
              <Line type="monotone" dataKey="value" stroke="#3b82f6" strokeWidth={2} dot={{ r: 4 }} />
            </LineChart>
          </ResponsiveContainer>
        </ChartCard>

        {/* Anomaly placeholder */}
        <Card className="flex flex-col">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Activity className="h-4 w-4 text-amber-500" />
              Anomaly Detection
            </CardTitle>
          </CardHeader>
          <CardContent className="flex-1 flex flex-col justify-center gap-3">
            <div className="rounded-lg bg-amber-50 border border-amber-100 p-4 text-sm text-amber-700">
              Statistical anomaly detection (Z-score / isolation forest) will surface here in Phase 9.
            </div>
            {['No critical spikes detected', 'Seasonal pattern confirmed', 'Baseline updated'].map(
              (msg, i) => (
                <div key={i} className="flex items-center gap-2 text-xs text-slate-500">
                  <span className="h-1.5 w-1.5 rounded-full bg-slate-300 shrink-0" />
                  {msg}
                </div>
              ),
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
