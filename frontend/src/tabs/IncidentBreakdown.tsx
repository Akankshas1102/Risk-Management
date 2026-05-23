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

const PIE_COLORS = ['#3b82f6','#10b981','#f59e0b','#6366f1','#ef4444','#8b5cf6','#14b8a6','#f97316','#ec4899','#0ea5e9','#84cc16','#f43f5e','#a78bfa','#fb923c','#22d3ee','#a3e635']

export function IncidentBreakdown() {
  const { selectedSite, selectedQuarter } = useFilters()

  const kpisQ   = useKpis(selectedSite, selectedQuarter)
  const catsQ   = useIncidentsByCategory(selectedSite, selectedQuarter)
  const siteQ   = useIncidentsBySite(selectedQuarter)
  const typeQ   = useIncidentsByType(selectedSite, selectedQuarter)
  const trendQ  = useIncidentTrend(selectedSite, 18)

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
              title="Top Category"
              value={kpis?.top_category?.split('/')[0] ?? '—'}
              subtitle={
                kpis?.top_category_share != null
                  ? `${(kpis.top_category_share * 100).toFixed(0)}% share`
                  : undefined
              }
            />
            <KpiCard title="Security" value="—" subtitle="from INCIDENTTYPENAME" />
            <KpiCard title="Non-Security" value="—" subtitle="from INCIDENTTYPENAME" />
            <KpiCard title="Categories" value={catsQ.data?.length ?? '—'} subtitle="distinct types" />
          </>
        )}
      </div>

      {/* ── Row 1: Donut + Bar by site ───────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Category donut */}
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
              <Pie
                data={catsQ.data ?? []}
                dataKey="count"
                nameKey="category"
                cx="50%"
                cy="50%"
                innerRadius={65}
                outerRadius={95}
                paddingAngle={2}
              >
                {(catsQ.data ?? []).map((_, i) => (
                  <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                ))}
              </Pie>
              <Tooltip formatter={(v: number) => [v, 'Incidents']} />
              <Legend iconSize={8} iconType="circle" wrapperStyle={{ fontSize: 10 }} />
            </PieChart>
          </ResponsiveContainer>
        </ChartCard>

        {/* Bar by site */}
        <ChartCard
          title="By Site"
          subtitle={selectedQuarter}
          loading={siteQ.isPending}
          error={siteQ.isError}
          onRetry={() => siteQ.refetch()}
          height={280}
        >
          <ResponsiveContainer width="100%" height={280}>
            <BarChart
              data={(siteQ.data ?? []).slice(0, 12)}
              layout="vertical"
              margin={{ top: 0, right: 20, bottom: 0, left: 60 }}
            >
              <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#f1f5f9" />
              <XAxis type="number" tick={{ fontSize: 10 }} tickLine={false} axisLine={false} />
              <YAxis
                type="category"
                dataKey="site"
                tick={{ fontSize: 9 }}
                tickLine={false}
                width={58}
                tickFormatter={(v: string) => v.slice(0, 12)}
              />
              <Tooltip />
              <Bar dataKey="count" fill="#3b82f6" radius={[0, 3, 3, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      {/* ── Row 2: Monthly trend + Type breakdown ────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Monthly trend */}
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
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
              <XAxis dataKey="month_label" tick={{ fontSize: 9 }} tickLine={false} interval={2} />
              <YAxis tick={{ fontSize: 10 }} tickLine={false} axisLine={false} />
              <Tooltip />
              <Line type="monotone" dataKey="count" stroke="#3b82f6" strokeWidth={2} dot={false} name={selectedSite} />
              <Line type="monotone" dataKey="all_sites_avg" stroke="#94a3b8" strokeWidth={1.5} strokeDasharray="4 4" dot={false} name="Avg" />
            </LineChart>
          </ResponsiveContainer>
        </ChartCard>

        {/* By type */}
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
                      <span className="text-slate-600 truncate max-w-[70%]" title={row.incident_type}>
                        {row.incident_type.replace('NON-SECURITY INCIDENTS-', 'NS-')}
                      </span>
                      <span className="font-semibold text-slate-700 tabular-nums">{row.count}</span>
                    </div>
                    <div className="h-1.5 bg-slate-100 rounded-full overflow-hidden">
                      <div
                        className="h-full rounded-full"
                        style={{
                          width: `${pct}%`,
                          backgroundColor: ['#3b82f6', '#10b981', '#f59e0b', '#6366f1'][i % 4],
                        }}
                      />
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
