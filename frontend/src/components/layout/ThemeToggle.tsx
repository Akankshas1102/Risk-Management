import { Moon, Sun } from 'lucide-react'
import { useTheme } from '@/context/ThemeContext'
import { cn } from '@/lib/utils'

export function ThemeToggle() {
  const { theme, toggleTheme } = useTheme()
  const isDark = theme === 'dark'

  return (
    <button
      onClick={toggleTheme}
      role="switch"
      aria-checked={isDark}
      aria-label="Toggle dark mode"
      title={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
      className={cn(
        'relative inline-flex h-9 w-16 items-center rounded-full border border-border',
        'transition-colors duration-300 focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 focus:ring-offset-background',
        isDark ? 'bg-secondary' : 'bg-muted',
      )}
    >
      {/* track icons */}
      <Sun
        className={cn(
          'absolute left-2 h-4 w-4 transition-opacity',
          isDark ? 'opacity-40 text-muted-foreground' : 'opacity-0',
        )}
      />
      <Moon
        className={cn(
          'absolute right-2 h-4 w-4 transition-opacity',
          isDark ? 'opacity-0' : 'opacity-40 text-muted-foreground',
        )}
      />
      {/* sliding knob */}
      <span
        className={cn(
          'inline-flex h-7 w-7 transform items-center justify-center rounded-full bg-card shadow-md',
          'transition-transform duration-300',
          isDark ? 'translate-x-8' : 'translate-x-1',
        )}
      >
        {isDark ? (
          <Moon className="h-4 w-4 text-primary" />
        ) : (
          <Sun className="h-4 w-4 text-warning" />
        )}
      </span>
    </button>
  )
}
