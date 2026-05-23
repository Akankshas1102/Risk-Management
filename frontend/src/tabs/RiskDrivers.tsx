import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  Cell,
} from 'recharts'
import { TrendingUp, TrendingDown, Minus, AlertTriangle } from 'lucide-react'
import { useFilters } from '@/context/FilterContext'
import { useDrivers } from '@/api/hooks'
import { KpiCard } from '@/components/common/KpiCard'
import { ChartCard } from '@/components/common/ChartCard'
import { SkeletonKpiRow, SkeletonTable } from '@/components/common/SkeletonGrid'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { cn } from '@/lib/utils'
import type { DriverItem } from '@/types/api'

function TrendChip({ trend }: { trend: string | null }) {
  if (trend === 'up')
    return (
      <span className="flex items-center gap-0.5 text-xs font-medium text-red-600 bg-red-50 rounded-full px-2 py-0.5">
        <TrendingUp className="h-3 w-3" /> Up
      </span>
    )
  if (trend === 'down')
    return (
      <span className="flex items-center gap-0.5 text-xs font-medium text-green-600 bg-green-50 rounded-full px-2 py-0.5">
        <TrendingDown className="h-3 w-3" /> Down
      </span>
    )
  return (
    <span className="flex items-center gap-0.5 text-xs text-slate-400 bg-slate-50 rounded-full px-2 py-0.5">
      <Minus className="h-3 w-3" /> Flat
    </span>
  )
}

function ImpactBar({ score }: { score: number }) {
  const color =
    score >= 70 ? '#ef4444' : score >= 40 ? '#f59e0b' : '#3b82f6'
  return (
    <div className="flex items-center gap-2 w-full">
      <div className="flex-1 h-2 bg-slate-100 rounded-full overflow-hidden">
        <div className="h-full rounded-full" style={{ width: `${score}%`, backgroundColor: color }} />
      </div>
      <span className="text-xs font-semibold tabular-nums text-slate-700 w-8 text-right">
        {score.toFixed(0)}
      </span>
    </div>
  )
}

export function RiskDrivers() {
  const { selectedSite, selectedQuarter } = useFilters()
  const drvQ = useDrivers(selectedSite, selectedQuarter)

  const drivers: DriverItem[] = drvQ.data ?? []
  const top3 = drivers.slice(0, 3)
  const topDriver = drivers[0]

  const risingCount = drivers.filter((d) => d.trend === 'up').length
  const criticalCount = drivers.filter((d) => (d.impact_score ?? 0) >= 70).length

  return (
    <div className="space-y-6">
      {/* ── KPI Row ─────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {drvQ.isPending ? (
          <SkeletonKpiRow count={4} />
        ) : (
          <>
            <KpiCard
              title="Drivers Identified"
              value={drivers.length}
              subtitle={selectedQuarter}
            />
            <KpiCard
              title="Top Driver"
              value={topDriver?.driver_name?.split('/')[0] ?? '—'}
              subtitle={
                topDriver?.impact_score != null
                  ? `impact ${topDriver.impact_score.toFixed(0)}/100`
                  : undefined
              }
              accentColor="border-l-red-500"
            />
            <KpiCard
              title="Rising Drivers"
              value={risingCount}
              subtitle="trend = up"
              accentColor="border-l-amber-500"
            />
            <KpiCard
              title="Critical Impact"
              value={criticalCount}
              subtitle="score ≥ 70"
              accentColor="border-l-orange-500"
            />
          </>
        )}
      </div>

      {/* ── Drivers table + Bar chart ─────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        {/* Table */}
        <Card className="lg:col-span-3 flex flex-col">
          <CardHeader>
            <CardTitle>Driver Attribution (SHAP)</CardTitle>
          </CardHeader>
          <CardContent className="p-0 flex-1">
            {drvQ.isPending ? (
              <div className="px-5 pb-5">
                <SkeletonTable rows={8} />
              </div>
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-100">
                    <th className="px-5 py-2.5 text-left text-xs font-medium text-slate-400 uppercase">
                      Category
                    </th>
                    <th className="px-5 py-2.5 text-left text-xs font-medium text-slate-400 uppercase w-44">
                      Impact
                    </th>
                    <th className="px-5 py-2.5 text-left text-xs font-medium text-slate-400 uppercase">
                      Trend
                    </th>
                    <th className="px-5 py-2.5 text-right text-xs font-medium text-slate-400 uppercase">
                      QoQ %
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {drivers.slice(0, 10).map((d, i) => (
                    <tr
                      key={d.id}
                      className={cn(
                        'border-b border-slate-50 hover:bg-slate-50',
                        i === 0 && 'bg-red-50/40',
                      )}
                    >
                      <td className="px-5 py-2.5 font-medium text-slate-700 max-w-[160px]">
                        <span className="truncate block" title={d.driver_name ?? ''}>
                          {d.driver_name ?? '—'}
                        </span>
                      </td>
                      <td className="px-5 py-2.5 w-44">
                        <ImpactBar score={d.impact_score ?? 0} />
                      </td>
                      <td className="px-5 py-2.5">
                        <TrendChip trend={d.trend} />
                      </td>
                      <td
                        className={cn(
                          'px-5 py-2.5 text-right text-xs font-semibold tabular-nums',
                          (d.pct_change_vs_last_qtr ?? 0) > 0 ? 'text-red-600' : 'text-green-600',
                        )}
                      >
                        {d.pct_change_vs_last_qtr != null
                          ? `${d.pct_change_vs_last_qtr > 0 ? '+' : ''}${d.pct_change_vs_last_qtr.toFixed(1)}%`
                          : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </CardContent>
        </Card>

        {/* Bar chart */}
        <ChartCard
          title="Top Drivers"
          subtitle="by impact score"
          loading={drvQ.isPending}
          error={drvQ.isError}
          onRetry={() => drvQ.refetch()}
          height={320}
          className="lg:col-span-2"
        >
          <ResponsiveContainer width="100%" height={320}>
            <BarChart
              data={drivers.slice(0, 8).map((d) => ({
                name: (d.driver_name ?? '').slice(0, 16),
                score: d.impact_score ?? 0,
                trend: d.trend,
              }))}
              layout="vertical"
              margin={{ top: 0, right: 20, bottom: 0, left: 80 }}
            >
              <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#f1f5f9" />
              <XAxis type="number" domain={[0, 100]} tick={{ fontSize: 10 }} tickLine={false} />
              <YAxis type="category" dataKey="name" tick={{ fontSize: 9 }} tickLine={false} width={78} />
              <Tooltip formatter={(v: number) => [v.toFixed(1), 'Impact score']} />
              <Bar dataKey="score" radius={[0, 3, 3, 0]}>
                {drivers.slice(0, 8).map((d, i) => (
                  <Cell
                    key={i}
                    fill={
                      (d.impact_score ?? 0) >= 70
                        ? '#ef4444'
                        : (d.impact_score ?? 0) >= 40
                        ? '#f59e0b'
                        : '#3b82f6'
                    }
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      {/* ── Focus area callout ───────────────────────────────────── */}
      {topDriver && (
        <Card className="border-l-4 border-l-red-500 bg-red-50/30">
          <CardContent className="py-4 flex items-start gap-3">
            <AlertTriangle className="h-5 w-5 text-red-500 shrink-0 mt-0.5" />
            <div>
              <p className="text-sm font-semibold text-slate-800">
                Focus Area: {topDriver.driver_name}
              </p>
              <p className="text-sm text-slate-600 mt-0.5">
                This category has the highest SHAP impact score ({(topDriver.impact_score ?? 0).toFixed(1)}/100)
                for {selectedSite} in {selectedQuarter}.
                {topDriver.trend === 'up' &&
                  ` The trend is rising (+${topDriver.pct_change_vs_last_qtr?.toFixed(1) ?? '?'}% QoQ).`}
              </p>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
