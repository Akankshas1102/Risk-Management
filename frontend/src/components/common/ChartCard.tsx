import React from 'react'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { AlertCircle, RefreshCw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

interface ChartCardProps {
  title: string
  subtitle?: string
  loading?: boolean
  error?: boolean
  onRetry?: () => void
  className?: string
  height?: number
  children: React.ReactNode
  headerRight?: React.ReactNode
}

export function ChartCard({
  title,
  subtitle,
  loading,
  error,
  onRetry,
  className,
  height = 240,
  children,
  headerRight,
}: ChartCardProps) {
  return (
    <Card className={cn('flex flex-col card-hover animate-fade-rise', className)}>
      <CardHeader className="flex-row items-start justify-between">
        <div>
          <CardTitle>{title}</CardTitle>
          {subtitle && <p className="text-xs text-muted-foreground mt-0.5">{subtitle}</p>}
        </div>
        {headerRight}
      </CardHeader>
      <CardContent className="flex-1 min-h-0 pt-1">
        {loading ? (
          <Skeleton className="w-full rounded-lg" style={{ height }} />
        ) : error ? (
          <div
            className="flex flex-col items-center justify-center gap-2 text-muted-foreground"
            style={{ height }}
          >
            <AlertCircle className="h-8 w-8 opacity-50" />
            <p className="text-sm">Failed to load data</p>
            {onRetry && (
              <Button variant="outline" size="sm" onClick={onRetry}>
                <RefreshCw className="h-3.5 w-3.5 mr-1.5" /> Retry
              </Button>
            )}
          </div>
        ) : (
          children
        )}
      </CardContent>
    </Card>
  )
}
