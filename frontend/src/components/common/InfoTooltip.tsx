import { Info } from 'lucide-react'
import type { ReactNode } from 'react'

/**
 * Inline ⓘ icon that reveals a help tooltip on hover.
 *
 * Pure CSS (group-hover) — no JS state, no extra dependency.
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
      <Info className="h-3.5 w-3.5 text-slate-400 hover:text-slate-600 cursor-help" />
      <span
        className={`absolute left-1/2 -translate-x-1/2 top-full mt-1 ${width}
                    rounded-lg border border-slate-200 bg-white px-3 py-2
                    shadow-lg text-xs text-slate-600 leading-relaxed
                    hidden group-hover:block z-50`}
      >
        {children}
      </span>
    </span>
  )
}
