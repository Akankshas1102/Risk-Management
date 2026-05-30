import React from 'react'
import { cn } from '@/lib/utils'

type DivProps = React.HTMLAttributes<HTMLDivElement>

export function Card({ className, ...props }: DivProps) {
  return (
    <div
      className={cn(
        'bg-card text-card-foreground rounded-xl border border-border shadow-sm',
        className,
      )}
      {...props}
    />
  )
}

export function CardHeader({ className, ...props }: DivProps) {
  return <div className={cn('flex flex-col space-y-1 p-5 pb-3', className)} {...props} />
}

export function CardTitle({ className, ...props }: DivProps) {
  return (
    <h3
      className={cn('text-sm font-semibold text-muted-foreground uppercase tracking-wide', className)}
      {...props}
    />
  )
}

export function CardContent({ className, ...props }: DivProps) {
  return <div className={cn('p-5 pt-2', className)} {...props} />
}
