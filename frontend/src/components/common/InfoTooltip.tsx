import { Info } from 'lucide-react'
import type { ReactNode } from 'react'

/**
 * Inline ⓘ icon that reveals a help tooltip on hover.
 * Pure CSS (group-hover) — no JS state, theme-aware.
 */
export function InfoTooltip({
  children,
  width = 'w-72',
}: {
  children: ReactNode
  width?: string
}) {
  return (
    <span className="relative group inline-flex items-center align-middle ml-1">
      <Info className="h-3.5 w-3.5 text-muted-foreground hover:text-foreground cursor-help" />
      <span
        className={`absolute left-1/2 -translate-x-1/2 top-full mt-1 ${width}
                    rounded-lg border border-border bg-popover px-3 py-2
                    shadow-lg text-xs text-popover-foreground leading-relaxed
                    hidden group-hover:block z-50`}
      >
        {children}
      </span>
    </span>
  )
}
