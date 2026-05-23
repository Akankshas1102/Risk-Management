import { TrendingUp, TrendingDown, Minus } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'

interface KpiCardProps {
  title: string
  value: string | number | null
  delta?: number | null
  subtitle?: string
  loading?: boolean
  accentColor?: string
}

export function KpiCard({ title, value, delta, subtitle, loading, accentColor }: KpiCardProps) {
  if (loading) {
    return (
      <Card className="p-5 space-y-3">
        <Skeleton className="h-3 w-24" />
        <Skeleton className="h-8 w-16" />
        <Skeleton className="h-3 w-20" />
      </Card>
    )
  }

  const deltaPositive = (delta ?? 0) > 0
  const deltaZero = delta == null || delta === 0

  return (
    <Card className={cn('p-5 border-l-4', accentColor ?? 'border-l-brand-500')}>
      <CardContent className="p-0 space-y-1">
        <p className="text-xs font-semibold text-slate-400 uppercase tracking-widest">{title}</p>
        <p className="text-3xl font-bold text-slate-900 tabular-nums leading-none">
          {value ?? '—'}
        </p>
        {(delta != null || subtitle) && (
          <div className="flex items-center gap-1.5 pt-1">
            {delta != null && !deltaZero && (
              <span
                className={cn(
                  'flex items-center gap-0.5 text-xs font-medium rounded-full px-1.5 py-0.5',
                  deltaPositive ? 'bg-red-50 text-red-600' : 'bg-green-50 text-green-600',
                )}
              >
                {deltaPositive ? (
                  <TrendingUp className="h-3 w-3" />
                ) : (
                  <TrendingDown className="h-3 w-3" />
                )}
                {Math.abs(delta).toFixed(1)}%
              </span>
            )}
            {deltaZero && delta === 0 && (
              <span className="flex items-center gap-0.5 text-xs font-medium bg-slate-50 text-slate-500 rounded-full px-1.5 py-0.5">
                <Minus className="h-3 w-3" />
                0%
              </span>
            )}
            {subtitle && <p className="text-xs text-slate-400">{subtitle}</p>}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
