import { useEffect, useState } from 'react'
import { useTheme } from '@/context/ThemeContext'

/**
 * Resolve the live CSS-variable colours into rgb() strings that Recharts
 * (which renders to SVG and can't read CSS vars on every attribute) can use.
 *
 * Re-reads whenever the theme flips so every chart restyles instantly.
 */
export interface ChartTheme {
  palette: string[]
  grid: string
  axis: string
  text: string
  primary: string
  success: string
  warning: string
  danger: string
  tooltipBg: string
  tooltipBorder: string
}

/** Read a channel-triplet CSS var like "164 143 255" → "rgb(164, 143, 255)". */
function readVar(name: string): string {
  if (typeof window === 'undefined') return '#888'
  const raw = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
  if (/^\d+\s+\d+\s+\d+$/.test(raw)) {
    const [r, g, b] = raw.split(/\s+/)
    return `rgb(${r}, ${g}, ${b})`
  }
  return raw || '#888'
}

export function useChartTheme(): ChartTheme {
  const { theme } = useTheme()
  const [, setVersion] = useState(0)

  // Force a re-read on the tick after the .dark class flips
  useEffect(() => {
    const id = requestAnimationFrame(() => setVersion((v) => v + 1))
    return () => cancelAnimationFrame(id)
  }, [theme])

  return {
    palette: [
      readVar('--chart-1'),
      readVar('--chart-2'),
      readVar('--chart-3'),
      readVar('--chart-4'),
      readVar('--chart-5'),
    ],
    grid: readVar('--border'),
    axis: readVar('--muted-foreground'),
    text: readVar('--foreground'),
    primary: readVar('--primary'),
    success: readVar('--success'),
    warning: readVar('--warning'),
    danger: readVar('--danger'),
    tooltipBg: readVar('--popover'),
    tooltipBorder: readVar('--border'),
  }
}
