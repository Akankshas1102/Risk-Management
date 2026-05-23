import { cn, riskColor } from '@/lib/utils'

interface Props {
  band: string | null | undefined
  size?: 'sm' | 'md'
}

export function SeverityBadge({ band, size = 'md' }: Props) {
  const label = band ?? 'Unknown'
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full font-medium capitalize',
        size === 'sm' ? 'px-2 py-0.5 text-xs' : 'px-2.5 py-1 text-xs',
        riskColor(band),
      )}
    >
      {label}
    </span>
  )
}
