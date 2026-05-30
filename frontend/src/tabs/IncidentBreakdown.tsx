import {
  PieChart, Pie, Cell, Tooltip, Legend, ResponsiveContainer,
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
  LineChart, Line,
} from 'recharts'
import { useFilters } from '@/context/FilterContext'
import {
  useKpis, useIncidentsByCategory, useIncidentsBySite,
  useIncidentsByType, useIncidentTrend,
} from '@/api/hooks'
import { KpiCard } from '@/components/common/KpiCard'
import { ChartCard } from '@/components/common/ChartCard'
import { SkeletonKpiRow, SkeletonTable } from '@/components/common/SkeletonGrid'
import { useChartTheme } from '@/lib/useChartTheme'

// A broad categorical palette for the donut (extends the 5 theme chart colours).
function pieColors(base: string[]): string[] {
  const extra = ['#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#14b8a6', '#f97316', '#ec4899', '#0ea5e9', '#84cc16', '#f43f5e', '#22d3ee']
  return [...base, ...extra]
}

export function IncidentBreakdown() {
  const { selectedSite, selectedQuarter } = useFilters()

  const kpisQ   = useKpis(selectedSite, selectedQuarter)
  const catsQ   = useIncidentsByCategory(selectedSite, selectedQuarter)
  const siteQ   = useIncidentsBySite(selectedQuarter)
  const typeQ   = useIncidentsByType(selectedSite, selectedQuarter)
  const trendQ  = useIncidentTrend(selectedSite, 18)
  const ct = useChartTheme()
  const PIE = pieColors(ct.palette)

  const kpis = kpisQ.data

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
        {kpisQ.isPending ? (
          <SkeletonKpiRow count={5} />
        ) : (
          <>
            <KpiCard title="Total Incidents" value={kpis?.total_incidents_qtr ?? '—'} delta={kpis?.delta_vs_last_qtr_pct} subtitle="vs last quarter" />
            <KpiCard
              title="Top Category"
              value={kpis?.top_category?.split('/')[0] ?? '—'}
              subtitle={kpis?.top_category_share != null ? `${(kpis.top_category_share * 100).toFixed(0)}% share` : undefined}
            />
            <KpiCard title="Security" value="—" subtitle="from INCIDENTTYPENAME" />
            <KpiCard title="Non-Security" value="—" subtitle="from INCIDENTTYPENAME" />
            <KpiCard title="Categories" value={catsQ.data?.length ?? '—'} subtitle="distinct types" />
          </>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <ChartCard
          title="By Category"
          subtitle={`${selectedSite} · ${selectedQuarter}`}
          loading={catsQ.isPending}
          error={catsQ.isError}
          onRetry={() => catsQ.refetch()}
          height={280}
        >
          <ResponsiveContainer width="100%" height={280}>
            <PieChart>
              <Pie data={catsQ.data ?? []} dataKey="count" nameKey="category" cx="50%" cy="50%" innerRadius={65} outerRadius={95} paddingAngle={2}>
                {(catsQ.data ?? []).map((_, i) => (
                  <Cell key={i} fill={PIE[i % PIE.length]} />
                ))}
              </Pie>
              <Tooltip
                contentStyle={{ background: ct.tooltipBg, border: `1px solid ${ct.tooltipBorder}`, borderRadius: 8 }}
                formatter={(v: number) => [v, 'Incidents']}
              />
              <Legend iconSize={8} iconType="circle" wrapperStyle={{ fontSize: 10 }} />
            </PieChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard
          title="By Site"
          subtitle={selectedQuarter}
          loading={siteQ.isPending}
          error={siteQ.isError}
          onRetry={() => siteQ.refetch()}
          height={280}
        >
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={(siteQ.data ?? []).slice(0, 12)} layout="vertical" margin={{ top: 0, right: 20, bottom: 0, left: 60 }}>
              <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke={ct.grid} />
              <XAxis type="number" tick={{ fontSize: 10, fill: ct.axis }} tickLine={false} axisLine={false} />
              <YAxis type="category" dataKey="site" tick={{ fontSize: 9, fill: ct.axis }} tickLine={false} width={58} tickFormatter={(v: string) => v.slice(0, 12)} />
              <Tooltip contentStyle={{ background: ct.tooltipBg, border: `1px solid ${ct.tooltipBorder}`, borderRadius: 8 }} />
              <Bar dataKey="count" fill={ct.primary} radius={[0, 3, 3, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <ChartCard
          title="Monthly Trend"
          subtitle="Last 18 months"
          loading={trendQ.isPending}
          error={trendQ.isError}
          onRetry={() => trendQ.refetch()}
          height={240}
          className="lg:col-span-2"
        >
          <ResponsiveContainer width="100%" height={240}>
            <LineChart data={trendQ.data ?? []} margin={{ top: 10, right: 20, bottom: 0, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={ct.grid} />
              <XAxis dataKey="month_label" tick={{ fontSize: 9, fill: ct.axis }} tickLine={false} interval={2} />
              <YAxis tick={{ fontSize: 10, fill: ct.axis }} tickLine={false} axisLine={false} />
              <Tooltip contentStyle={{ background: ct.tooltipBg, border: `1px solid ${ct.tooltipBorder}`, borderRadius: 8 }} />
              <Line type="monotone" dataKey="count" stroke={ct.primary} strokeWidth={2} dot={false} name={selectedSite} />
              <Line type="monotone" dataKey="all_sites_avg" stroke={ct.axis} strokeWidth={1.5} strokeDasharray="4 4" dot={false} name="Avg" />
            </LineChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard
          title="By Type"
          subtitle={selectedQuarter}
          loading={typeQ.isPending}
          error={typeQ.isError}
          onRetry={() => typeQ.refetch()}
          height={240}
        >
          <div className="space-y-2 pt-1">
            {typeQ.isPending ? (
              <SkeletonTable rows={4} />
            ) : (
              (typeQ.data ?? []).map((row, i) => {
                const total = (typeQ.data ?? []).reduce((s, r) => s + r.count, 0)
                const pct = total > 0 ? (row.count / total) * 100 : 0
                return (
                  <div key={i} className="space-y-1">
                    <div className="flex items-center justify-between text-xs">
                      <span className="text-muted-foreground truncate max-w-[70%]" title={row.incident_type}>
                        {row.incident_type.replace('NON-SECURITY INCIDENTS-', 'NS-')}
                      </span>
                      <span className="font-semibold text-foreground tabular-nums">{row.count}</span>
                    </div>
                    <div className="h-1.5 bg-muted rounded-full overflow-hidden">
                      <div className="h-full rounded-full" style={{ width: `${pct}%`, backgroundColor: PIE[i % PIE.length] }} />
                    </div>
                  </div>
                )
              })
            )}
          </div>
        </ChartCard>
      </div>
    </div>
  )
}
