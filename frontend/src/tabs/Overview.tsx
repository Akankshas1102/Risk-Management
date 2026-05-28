import {
  PieChart, Pie, Cell, Tooltip, Legend, ResponsiveContainer,
  ScatterChart, Scatter, XAxis, YAxis, CartesianGrid, ZAxis,
  LineChart, Line, ReferenceDot,
} from 'recharts'
import { formatDistanceToNow } from 'date-fns'
import { Brain, Sparkles, Download, TrendingUp, TrendingDown, Minus } from 'lucide-react'
import { useFilters } from '@/context/FilterContext'
import {
  useKpis, useIncidentsByCategory, useHeatmap, useIncidentTrend,
  usePredictions, useRiskScores,
} from '@/api/hooks'
import { KpiCard } from '@/components/common/KpiCard'
import { ChartCard } from '@/components/common/ChartCard'
import { SeverityBadge } from '@/components/common/SeverityBadge'
import { SkeletonKpiRow } from '@/components/common/SkeletonGrid'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import type { KPIResponse, TrendPoint, RiskScoreItem } from '@/types/api'

const CHART_COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#6366f1', '#ef4444', '#8b5cf6', '#14b8a6', '#f97316']

// ---------------------------------------------------------------------------
// Left-rail helpers
// ---------------------------------------------------------------------------

function deriveLevel(score: number | null | undefined): string {
  if (score == null) return '—'
  if (score <= 40) return 'Low'
  if (score <= 65) return 'Medium'
  if (score <= 85) return 'High'
  return 'Critical'
}

function levelClasses(level: string): string {
  switch (level) {
    case 'Critical':
    case 'High':   return 'bg-red-100 text-red-700'
    case 'Medium': return 'bg-amber-100 text-amber-700'
    case 'Low':    return 'bg-green-100 text-green-700'
    default:       return 'bg-slate-100 text-slate-600'
  }
}

function StatRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-2 text-sm">
      <span className="text-slate-500 shrink-0">{label}</span>
      <span className="font-medium text-slate-800 text-right">{children}</span>
    </div>
  )
}

function TrendValue({ delta }: { delta: number | null | undefined }) {
  if (delta == null) {
    return <span className="flex items-center gap-1 text-slate-400"><Minus className="h-3.5 w-3.5" /> Stable</span>
  }
  if (delta > 0) {
    return <span className="flex items-center gap-1 text-red-600"><TrendingUp className="h-3.5 w-3.5" /> Increasing</span>
  }
  if (delta < 0) {
    return <span className="flex items-center gap-1 text-green-600"><TrendingDown className="h-3.5 w-3.5" /> Decreasing</span>
  }
  return <span className="flex items-center gap-1 text-slate-400"><Minus className="h-3.5 w-3.5" /> Stable</span>
}

function DeltaValue({ delta }: { delta: number | null | undefined }) {
  if (delta == null) return <span className="text-slate-400">—</span>
  const cls = delta > 0 ? 'text-red-600' : delta < 0 ? 'text-green-600' : 'text-slate-400'
  const Icon = delta > 0 ? TrendingUp : delta < 0 ? TrendingDown : Minus
  return (
    <span className={cn('flex items-center gap-1 tabular-nums', cls)}>
      <Icon className="h-3.5 w-3.5" />
      {delta > 0 ? '+' : ''}{delta.toFixed(1)}%
    </span>
  )
}

// ---------------------------------------------------------------------------
// Left rail panel
// ---------------------------------------------------------------------------

function LeftRail({
  site,
  kpis,
  trend,
  allRisk,
  loading,
}: {
  site: string
  kpis?: KPIResponse
  trend: TrendPoint[]
  allRisk: RiskScoreItem[]
  loading: boolean
}) {
  const siteRow = allRisk.find(
    (r) => (r.site ?? '').toUpperCase() === (site ?? '').toUpperCase(),
  )

  const score = kpis?.risk_score ?? siteRow?.risk_score ?? null
  const level = siteRow?.risk_level ?? deriveLevel(score)
  const bu = siteRow?.business_unit ?? '—'

  // Rank by risk score descending across all sites
  const ranked = [...allRisk]
    .filter((r) => r.risk_score != null)
    .sort((a, b) => (b.risk_score ?? 0) - (a.risk_score ?? 0))
  const rankIdx = siteRow ? ranked.findIndex((r) => r.site === siteRow.site) : -1
  const rankText = rankIdx >= 0 ? `${rankIdx + 1} / ${ranked.length} Sites` : '—'

  // Sparkline = last 6 months of the incident trend already fetched
  const spark = trend.slice(-6).map((t) => ({ label: t.month_label, value: t.count }))

  const delta = kpis?.delta_vs_last_qtr_pct

  return (
    <aside className="w-[280px] shrink-0">
      <Card className="overflow-hidden">
        {/* ── Hero ─────────────────────────────────────────────── */}
        <div className="h-28 bg-gradient-to-br from-slate-900 via-blue-900 to-blue-700 flex flex-col justify-end p-4">
          <h2 className="text-white font-bold text-base leading-tight truncate" title={site}>
            {site || '—'}
          </h2>
          <span className="mt-1 self-start rounded bg-white/15 px-2 py-0.5 text-[11px] font-medium text-white/90 backdrop-blur-sm">
            {bu}
          </span>
        </div>

        {/* ── Body ─────────────────────────────────────────────── */}
        <div className="p-4 space-y-4">
          {/* Risk score */}
          <div>
            <p className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
              Risk Score
            </p>
            <div className="flex items-center gap-2 mt-1">
              {loading ? (
                <Skeleton className="h-9 w-16" />
              ) : (
                <>
                  <span className="text-4xl font-bold text-slate-900 tabular-nums leading-none">
                    {score != null ? score.toFixed(1) : '—'}
                  </span>
                  <span className="text-sm text-slate-400">/100</span>
                  <span className={cn('ml-auto text-xs font-medium px-2 py-0.5 rounded-full', levelClasses(level))}>
                    {level}
                  </span>
                </>
              )}
            </div>

            {/* Sparkline (last 6 months) */}
            <div className="h-20 mt-2 -mx-1">
              {spark.length > 0 ? (
                <ResponsiveContainer width="100%" height={80}>
                  <LineChart data={spark} margin={{ top: 6, right: 4, bottom: 0, left: 4 }}>
                    <Line
                      type="monotone"
                      dataKey="value"
                      stroke="#3b82f6"
                      strokeWidth={2}
                      dot={false}
                      isAnimationActive={false}
                    />
                  </LineChart>
                </ResponsiveContainer>
              ) : (
                <div className="h-full flex items-center justify-center text-xs text-slate-300">
                  no trend data
                </div>
              )}
            </div>
          </div>

          {/* Stats list */}
          <div className="space-y-2.5 border-t border-slate-100 pt-3">
            <StatRow label="Risk Level">
              <span className={cn('text-xs font-medium px-2 py-0.5 rounded-full', levelClasses(level))}>
                {level}
              </span>
            </StatRow>
            <StatRow label="Trend"><TrendValue delta={delta} /></StatRow>
            <StatRow label="Rank">{rankText}</StatRow>
            <StatRow label="Incidents (This Qtr)">{kpis?.total_incidents_qtr ?? '—'}</StatRow>
            <StatRow label="vs Last Qtr"><DeltaValue delta={delta} /></StatRow>
            <StatRow label="Primary Category">
              <span className="truncate max-w-[150px] inline-block align-bottom" title={kpis?.top_category ?? ''}>
                {kpis?.top_category ?? '—'}
              </span>
            </StatRow>
          </div>

          {/* Download */}
          <Button
            variant="outline"
            className="w-full"
            onClick={() => window.alert('Export coming in Reports tab')}
          >
            <Download className="h-4 w-4 mr-2" /> Download Assessment
          </Button>
        </div>
      </Card>
    </aside>
  )
}

// ---------------------------------------------------------------------------
// Prediction KPI card with tooltip
// ---------------------------------------------------------------------------

function PredictedNextQtrCard({ site }: { site?: string }) {
  const predQ = usePredictions(site)

  if (!site) {
    return (
      <Card className="p-5 border-l-4 border-l-green-500">
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
      <Card className="p-5 border-l-4 border-l-green-500 cursor-default">
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
  const riskAllQ = useRiskScores()   // latest risk score per site (for BU, rank, level)

  const kpis = kpisQ.data

  // Split heatmap data so the selected site can be highlighted on top
  const heatData = heatQ.data ?? []
  const currentSiteData = heatData.filter(
    (d) => (d.site ?? '').toUpperCase() === (selectedSite ?? '').toUpperCase(),
  )
  const otherSitesData = heatData.filter(
    (d) => (d.site ?? '').toUpperCase() !== (selectedSite ?? '').toUpperCase(),
  )

  return (
    <div className="flex flex-col lg:flex-row gap-6 items-start">
      {/* ── LEFT RAIL ───────────────────────────────────────────── */}
      <LeftRail
        site={selectedSite}
        kpis={kpis}
        trend={trendQ.data ?? []}
        allRisk={riskAllQ.data ?? []}
        loading={kpisQ.isPending}
      />

      {/* ── MAIN CONTENT ────────────────────────────────────────── */}
      <div className="flex-1 min-w-0 space-y-6">
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
                accentColor="border-l-blue-500"
              />
              <KpiCard
                title="Risk Score"
                value={kpis?.risk_score != null ? kpis.risk_score.toFixed(1) : '—'}
                subtitle="composite index"
                accentColor="border-l-orange-500"
              />
              <KpiCard
                title="Open Incidents"
                value="—"
                subtitle="awaiting close-out"
                accentColor="border-l-purple-500"
              />
              <KpiCard
                title="Top Category"
                value={kpis?.top_category ?? '—'}
                subtitle={
                  kpis?.top_category_share != null
                    ? `${(kpis.top_category_share * 100).toFixed(0)}% of total`
                    : undefined
                }
                accentColor="border-l-teal-500"
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

                {/* Quadrant corner labels */}
                <ReferenceDot x={0.05} y={0.05} r={0} label={{ value: 'Low Risk', position: 'right', fill: '#16a34a', fontSize: 11 }} />
                <ReferenceDot x={0.05} y={0.95} r={0} label={{ value: 'Monitor', position: 'right', fill: '#d97706', fontSize: 11 }} />
                <ReferenceDot x={0.95} y={0.05} r={0} label={{ value: 'Watch', position: 'left', fill: '#d97706', fontSize: 11 }} />
                <ReferenceDot x={0.95} y={0.95} r={0} label={{ value: 'High Risk', position: 'left', fill: '#dc2626', fontSize: 11 }} />

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

                {/* Other sites — muted grey/blue, rendered underneath */}
                <Scatter
                  data={otherSitesData}
                  shape={(props: unknown) => {
                    const p = props as { cx: number; cy: number }
                    return (
                      <circle
                        cx={p.cx}
                        cy={p.cy}
                        r={6}
                        fill="#94a3b8"
                        fillOpacity={0.7}
                        stroke="white"
                        strokeWidth={1}
                      />
                    )
                  }}
                />

                {/* Selected site — highlighted on top with a name label */}
                <Scatter
                  data={currentSiteData}
                  shape={(props: unknown) => {
                    const p = props as { cx: number; cy: number; payload: { site: string } }
                    return (
                      <g>
                        <circle
                          cx={p.cx}
                          cy={p.cy}
                          r={10}
                          fill="#ef4444"
                          fillOpacity={0.95}
                          stroke="white"
                          strokeWidth={2}
                        />
                        <text
                          x={p.cx + 14}
                          y={p.cy + 4}
                          fontSize={11}
                          fontWeight={600}
                          fill="#ef4444"
                        >
                          {p.payload.site}
                        </text>
                      </g>
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
    </div>
  )
}
