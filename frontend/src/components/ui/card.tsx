import React from 'react'
import { cn } from '@/lib/utils'

type DivProps = React.HTMLAttributes<HTMLDivElement>

export function Card({ className, ...props }: DivProps) {
  return (
    <div
      className={cn('bg-white rounded-xl border border-slate-200 shadow-sm', className)}
      {...props}
    />
  )
}

export function CardHeader({ className, ...props }: DivProps) {
  return <div className={cn('flex flex-col space-y-1 p-5 pb-3', className)} {...props} />
}

export function CardTitle({ className, ...props }: DivProps) {
  return (
    <h3 className={cn('text-sm font-semibold text-slate-500 uppercase tracking-wide', className)} {...props} />
  )
}

export function CardContent({ className, ...props }: DivProps) {
  return <div className={cn('p-5 pt-2', className)} {...props} />
}
