import { CheckCircle2, Clock, Sparkles } from 'lucide-react'
import { useFilters } from '@/context/FilterContext'
import { useRecommendations } from '@/api/hooks'
import { KpiCard } from '@/components/common/KpiCard'
import { SkeletonKpiRow, SkeletonTable } from '@/components/common/SkeletonGrid'
import { ErrorState } from '@/components/common/ErrorState'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { cn } from '@/lib/utils'
import type { RecommendationItem } from '@/types/api'

function PriorityDot({ priority }: { priority: string | null }) {
  const colors: Record<string, string> = {
    high:   'bg-danger',
    medium: 'bg-warning',
    low:    'bg-success',
  }
  return (
    <span className={cn('inline-block h-2 w-2 rounded-full shrink-0', colors[priority ?? ''] ?? 'bg-muted-foreground/40')} />
  )
}

function PriorityBadge({ priority }: { priority: string | null }) {
  const styles: Record<string, string> = {
    high:   'bg-danger/10 text-danger border-danger/20',
    medium: 'bg-warning/10 text-warning border-warning/20',
    low:    'bg-success/10 text-success border-success/20',
  }
  return (
    <span className={cn(
      'inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-medium capitalize',
      styles[priority ?? ''] ?? 'bg-muted text-muted-foreground border-border',
    )}>
      <PriorityDot priority={priority} />
      {priority ?? 'Unknown'}
    </span>
  )
}

export function Recommendations() {
  const { selectedSite, selectedQuarter } = useFilters()
  const recQ = useRecommendations(selectedSite, selectedQuarter)

  const recs: RecommendationItem[] = recQ.data ?? []
  const highCount   = recs.filter((r) => r.priority === 'high').length
  const mediumCount = recs.filter((r) => r.priority === 'medium').length
  const lowCount    = recs.filter((r) => r.priority === 'low').length

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {recQ.isPending ? (
          <SkeletonKpiRow count={3} />
        ) : (
          <>
            <KpiCard title="High Priority" value={highCount} subtitle="immediate action" accentColor="border-l-danger" />
            <KpiCard title="Medium Priority" value={mediumCount} subtitle="plan within quarter" accentColor="border-l-warning" />
            <KpiCard title="Low Priority" value={lowCount} subtitle="monitor & review" accentColor="border-l-success" />
          </>
        )}
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Recommended Actions</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {recQ.isPending ? (
            <div className="px-5 pb-5"><SkeletonTable rows={6} /></div>
          ) : recQ.isError ? (
            <div className="px-5 pb-5"><ErrorState onRetry={() => recQ.refetch()} /></div>
          ) : recs.length === 0 ? (
            <div className="flex flex-col items-center gap-2 py-12 text-muted-foreground">
              <CheckCircle2 className="h-10 w-10 text-success/60" />
              <p className="text-sm">No open recommendations for this site and quarter.</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border">
                    <th className="px-5 py-3 text-left text-xs font-medium text-muted-foreground uppercase">Priority</th>
                    <th className="px-5 py-3 text-left text-xs font-medium text-muted-foreground uppercase">Action</th>
                    <th className="px-5 py-3 text-left text-xs font-medium text-muted-foreground uppercase hidden md:table-cell">Impact Estimate</th>
                    <th className="px-5 py-3 text-left text-xs font-medium text-muted-foreground uppercase hidden lg:table-cell">Owner</th>
                    <th className="px-5 py-3 text-left text-xs font-medium text-muted-foreground uppercase hidden lg:table-cell">Source</th>
                    <th className="px-5 py-3 text-left text-xs font-medium text-muted-foreground uppercase">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {recs.map((r) => (
                    <tr key={r.id} className="border-b border-border/50 hover:bg-muted/50">
                      <td className="px-5 py-3.5"><PriorityBadge priority={r.priority} /></td>
                      <td className="px-5 py-3.5 font-medium text-foreground max-w-xs">{r.action_text ?? '—'}</td>
                      <td className="px-5 py-3.5 text-muted-foreground text-xs hidden md:table-cell max-w-[200px]">{r.impact_estimate || '—'}</td>
                      <td className="px-5 py-3.5 text-muted-foreground text-xs hidden lg:table-cell">{r.suggested_owner || '—'}</td>
                      <td className="px-5 py-3.5 hidden lg:table-cell">
                        {r.source === 'llm' ? (
                          <span className="inline-flex items-center gap-1 text-xs text-primary bg-primary/10 px-2 py-0.5 rounded-full">
                            <Sparkles className="h-3 w-3" /> AI
                          </span>
                        ) : (
                          <span className="text-xs text-muted-foreground bg-muted px-2 py-0.5 rounded-full">Rules</span>
                        )}
                      </td>
                      <td className="px-5 py-3.5">
                        {r.status === 'open' ? (
                          <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
                            <Clock className="h-3.5 w-3.5" /> Open
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 text-xs text-success">
                            <CheckCircle2 className="h-3.5 w-3.5" /> Done
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      <Card className="border border-dashed border-primary/30 bg-primary/5">
        <CardContent className="py-5 flex items-start gap-3">
          <Sparkles className="h-5 w-5 text-primary shrink-0 mt-0.5" />
          <div>
            <p className="text-sm font-semibold text-primary">AI Executive Summary</p>
            <p className="text-sm text-primary/80 mt-1">
              LLM-generated summary of risk recommendations will appear here in Phase 9.
            </p>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
