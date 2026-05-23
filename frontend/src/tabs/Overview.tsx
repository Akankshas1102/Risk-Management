import {
  PieChart, Pie, Cell, Tooltip, Legend, ResponsiveContainer,
  ScatterChart, Scatter, XAxis, YAxis, CartesianGrid, ZAxis,
  LineChart, Line,
} from 'recharts'
import { formatDistanceToNow } from 'date-fns'
import { Brain, Sparkles } from 'lucide-react'
import { useFilters } from '@/context/FilterContext'
import { useKpis, useIncidentsByCategory, useHeatmap, useIncidentTrend, usePredictions } from '@/api/hooks'
import { KpiCard } from '@/components/common/KpiCard'
import { ChartCard } from '@/components/common/ChartCard'
import { SeverityBadge } from '@/components/common/SeverityBadge'
import { SkeletonKpiRow } from '@/components/common/SkeletonGrid'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { cn, riskDot } from '@/lib/utils'

const CHART_COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#6366f1', '#ef4444', '#8b5cf6', '#14b8a6', '#f97316']

// ---------------------------------------------------------------------------
// Prediction KPI card with tooltip
// ---------------------------------------------------------------------------

function PredictedNextQtrCard({ site }: { site?: string }) {
  const predQ = usePredictions(site)

  if (!site) {
    return (
      <Card className="p-5 border-l-4 border-l-slate-400">
        <div className="p-0 space-y-1">
          <p className="text-xs font-semibold text-slate-400 uppercase tracking-widest">
            Predicted Next Qtr
          </p>
          <p className="text-3xl font-bold text-slate-900 tabular-nums leading-none">—</p>
          <p className="text-xs text-slate-400 pt-1">ML forecast</p>
        </div>
      </Card>
    )
  }

  if (predQ.isPending) {
    return (
      <Card className="p-5 space-y-3">
        <Skeleton className="h-3 w-24" />
        <Skeleton className="h-8 w-16" />
        <Skeleton className="h-3 w-20" />
      </Card>
    )
  }

  const preds = predQ.data?.predictions ?? []
  const meta  = predQ.data?.model_meta
  const nextPred = preds.length > 0 ? preds[0] : null

  const hasPrediction = nextPred && (nextPred.predicted_count ?? 0) > 0

  const trainedStr = meta?.last_trained_at
    ? formatDistanceToNow(new Date(meta.last_trained_at), { addSuffix: true })
    : null

  const tooltipLines = [
    meta?.champion_model && `Model: ${meta.champion_model}`,
    nextPred?.confidence_band && `Confidence: ${nextPred.confidence_band}`,
    trainedStr && `Trained ${trainedStr}`,
    nextPred?.target_quarter && `For ${nextPred.target_quarter}`,
  ].filter(Boolean) as string[]

  return (
    <div className="relative group">
      <Card className="p-5 border-l-4 border-l-slate-400 cursor-default">
        <div className="p-0 space-y-1">
          <p className="text-xs font-semibold text-slate-400 uppercase tracking-widest">
            Predicted Next Qtr
          </p>
          <p className="text-3xl font-bold text-slate-900 tabular-nums leading-none">
            {hasPrediction
              ? Math.round(nextPred!.predicted_count!)
              : 'Insufficient history'}
          </p>
          <div className="flex items-center gap-1.5 pt-1">
            {nextPred?.confidence_band && (
              <SeverityBadge band={nextPred.confidence_band} size="sm" />
            )}
            <p className="text-xs text-slate-400">ML forecast</p>
          </div>
        </div>
      </Card>
      {tooltipLines.length > 0 && (
        <div className={cn(
          'absolute left-0 top-full mt-1 z-50 w-52 rounded-lg border border-slate-200 bg-white px-3 py-2 shadow-lg',
          'text-xs text-slate-600 space-y-1',
          'hidden group-hover:block',
        )}>
          {tooltipLines.map((line) => (
            <p key={line}>{line}</p>
          ))}
        </div>
      )}
    </div>
  )
}

export function Overview() {
  const { selectedSite, selectedQuarter } = useFilters()

  const kpisQ = useKpis(selectedSite, selectedQuarter)
  const catsQ = useIncidentsByCategory(selectedSite, selectedQuarter)
  const heatQ = useHeatmap(selectedQuarter)
  const trendQ = useIncidentTrend(selectedSite, 12)

  const kpis = kpisQ.data

  return (
    <div className="space-y-6">
      {/* ── KPI Row ─────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
        {kpisQ.isPending ? (
          <SkeletonKpiRow count={5} />
        ) : (
          <>
            <KpiCard
              title="Total Incidents"
              value={kpis?.total_incidents_qtr ?? '—'}
              delta={kpis?.delta_vs_last_qtr_pct}
              subtitle="vs last quarter"
            />
            <KpiCard
              title="Risk Score"
              value={kpis?.risk_score != null ? kpis.risk_score.toFixed(1) : '—'}
              subtitle="composite index"
              accentColor={
                (kpis?.risk_score ?? 0) >= 66
                  ? 'border-l-red-500'
                  : (kpis?.risk_score ?? 0) >= 41
                  ? 'border-l-amber-500'
                  : 'border-l-green-500'
              }
            />
            <KpiCard
              title="Open Incidents"
              value="—"
              subtitle="awaiting close-out"
              accentColor="border-l-orange-400"
            />
            <KpiCard
              title="Top Category"
              value={kpis?.top_category ?? '—'}
              subtitle={
                kpis?.top_category_share != null
                  ? `${(kpis.top_category_share * 100).toFixed(0)}% of total`
                  : undefined
              }
              accentColor="border-l-indigo-500"
            />
            <PredictedNextQtrCard site={selectedSite} />
          </>
        )}
      </div>

      {/* ── Charts Row 1 ────────────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Donut */}
        <ChartCard
          title="Incident Mix"
          subtitle={selectedQuarter}
          loading={catsQ.isPending}
          error={catsQ.isError}
          onRetry={() => catsQ.refetch()}
          height={260}
        >
          <ResponsiveContainer width="100%" height={260}>
            <PieChart>
              <Pie
                data={catsQ.data ?? []}
                dataKey="count"
                nameKey="category"
                cx="50%"
                cy="50%"
                innerRadius={60}
                outerRadius={90}
                paddingAngle={2}
              >
                {(catsQ.data ?? []).map((_, i) => (
                  <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />
                ))}
              </Pie>
              <Tooltip formatter={(v: number) => [v, 'Incidents']} />
              <Legend iconSize={8} iconType="circle" wrapperStyle={{ fontSize: 11 }} />
            </PieChart>
          </ResponsiveContainer>
        </ChartCard>

        {/* Heatmap */}
        <ChartCard
          title="Risk Heatmap"
          subtitle="Likelihood vs Impact by site"
          loading={heatQ.isPending}
          error={heatQ.isError}
          onRetry={() => heatQ.refetch()}
          height={260}
          className="lg:col-span-2"
        >
          <ResponsiveContainer width="100%" height={260}>
            <ScatterChart margin={{ top: 10, right: 20, bottom: 20, left: 10 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
              <XAxis
                type="number"
                dataKey="likelihood_score"
                domain={[0, 1]}
                name="Likelihood"
                label={{ value: 'Likelihood', position: 'bottom', fontSize: 11, fill: '#94a3b8' }}
                tick={{ fontSize: 10 }}
              />
              <YAxis
                type="number"
                dataKey="impact_score"
                domain={[0, 1]}
                name="Impact"
                label={{ value: 'Impact', angle: -90, position: 'left', fontSize: 11, fill: '#94a3b8' }}
                tick={{ fontSize: 10 }}
              />
              <ZAxis range={[60, 60]} />
              <Tooltip
                cursor={false}
                content={({ payload }) => {
                  if (!payload?.length) return null
                  const d = payload[0].payload as { site: string; risk_band: string; likelihood_score: number; impact_score: number }
                  return (
                    <div className="bg-white border border-slate-200 rounded-lg p-2 shadow-lg text-xs space-y-1">
                      <p className="font-semibold text-slate-700">{d.site}</p>
                      <p className="text-slate-500">Likelihood: {d.likelihood_score.toFixed(2)}</p>
                      <p className="text-slate-500">Impact: {d.impact_score.toFixed(2)}</p>
                      <SeverityBadge band={d.risk_band} size="sm" />
                    </div>
                  )
                }}
              />
              <Scatter
                data={heatQ.data ?? []}
                shape={(props: unknown) => {
                  const p = props as { cx: number; cy: number; payload: { risk_band: string } }
                  return (
                    <circle
                      cx={p.cx}
                      cy={p.cy}
                      r={9}
                      fill={riskDot(p.payload.risk_band)}
                      fillOpacity={0.8}
                      stroke="white"
                      strokeWidth={1.5}
                    />
                  )
                }}
              />
            </ScatterChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      {/* ── Charts Row 2 ────────────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* 12-month trend */}
        <ChartCard
          title="12-Month Trend"
          subtitle="Site vs all-sites average"
          loading={trendQ.isPending}
          error={trendQ.isError}
          onRetry={() => trendQ.refetch()}
          height={220}
          className="lg:col-span-2"
        >
          <ResponsiveContainer width="100%" height={220}>
            <LineChart
              data={trendQ.data ?? []}
              margin={{ top: 10, right: 20, bottom: 0, left: 0 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
              <XAxis dataKey="month_label" tick={{ fontSize: 10 }} tickLine={false} />
              <YAxis tick={{ fontSize: 10 }} tickLine={false} axisLine={false} />
              <Tooltip
                formatter={(v: number, name: string) => [
                  v,
                  name === 'count' ? selectedSite : 'All sites avg',
                ]}
              />
              <Legend iconSize={8} wrapperStyle={{ fontSize: 11 }} />
              <Line
                type="monotone"
                dataKey="count"
                stroke="#3b82f6"
                strokeWidth={2}
                dot={false}
                name="Site"
              />
              <Line
                type="monotone"
                dataKey="all_sites_avg"
                stroke="#94a3b8"
                strokeWidth={1.5}
                strokeDasharray="4 4"
                dot={false}
                name="Average"
              />
            </LineChart>
          </ResponsiveContainer>
        </ChartCard>

        {/* AI Insight Placeholder */}
        <Card className="flex flex-col">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Sparkles className="h-4 w-4 text-brand-500" />
              AI Insight
            </CardTitle>
          </CardHeader>
          <CardContent className="flex-1 flex flex-col justify-between gap-4">
            <div className="rounded-lg bg-brand-50 border border-brand-100 p-4 space-y-2">
              <div className="flex items-start gap-2">
                <Brain className="h-4 w-4 text-brand-500 mt-0.5 shrink-0" />
                <p className="text-sm text-slate-600">
                  AI-powered narrative insights will appear here after Phase 9 LLM integration.
                </p>
              </div>
            </div>
            <div className="space-y-2">
              {['Access Control trend↑', 'Reporting lag improving', 'Q4 forecast: moderate'].map(
                (item, i) => (
                  <div
                    key={i}
                    className="flex items-center gap-2 rounded-md bg-slate-50 px-3 py-2 text-xs text-slate-500"
                  >
                    <span className="h-1.5 w-1.5 rounded-full bg-brand-400 shrink-0" />
                    {item}
                  </div>
                ),
              )}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
