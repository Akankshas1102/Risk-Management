import {
  LayoutDashboard,
  TrendingUp,
  BarChart2,
  Activity,
  Cpu,
  ClipboardList,
  Brain,
  FileText,
  ChevronLeft,
  ShieldAlert,
  Wrench,
} from 'lucide-react'
import { cn } from '@/lib/utils'

export type TabId =
  | 'overview'
  | 'risk-drivers'
  | 'incident-breakdown'
  | 'trends'
  | 'predictions'
  | 'recommendations'
  | 'ai-insights'
  | 'reports'
  | 'data-health'

interface NavItem {
  id: TabId
  label: string
  icon: React.ElementType
  group?: 'main' | 'admin'
}

const NAV_ITEMS: NavItem[] = [
  { id: 'overview',            label: 'Overview',            icon: LayoutDashboard, group: 'main' },
  { id: 'risk-drivers',        label: 'Risk Drivers',        icon: TrendingUp,      group: 'main' },
  { id: 'incident-breakdown',  label: 'Breakdown',           icon: BarChart2,       group: 'main' },
  { id: 'trends',              label: 'Trends',              icon: Activity,        group: 'main' },
  { id: 'predictions',         label: 'Predictions',         icon: Cpu,             group: 'main' },
  { id: 'recommendations',     label: 'Recommendations',     icon: ClipboardList,   group: 'main' },
  { id: 'ai-insights',         label: 'AI Insights',         icon: Brain,           group: 'main' },
  { id: 'reports',             label: 'Reports',             icon: FileText,        group: 'main' },
  { id: 'data-health',         label: 'Data & Model Health', icon: Wrench,          group: 'admin' },
]

interface SidebarProps {
  activeTab: TabId
  onTabChange: (tab: TabId) => void
  collapsed: boolean
  onToggle: () => void
}

export function Sidebar({ activeTab, onTabChange, collapsed, onToggle }: SidebarProps) {
  return (
    <aside
      className={cn(
        'fixed inset-y-0 left-0 z-40 flex flex-col bg-sidebar text-sidebar-foreground border-r border-sidebar-border transition-all duration-200',
        collapsed ? 'w-16' : 'w-56',
      )}
    >
      {/* Logo */}
      <div className="flex h-16 items-center gap-3 px-4 border-b border-sidebar-border">
        <div className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-sidebar-accent/15">
          <ShieldAlert className="h-5 w-5 text-sidebar-accent" />
        </div>
        {!collapsed && (
          <span className="text-sm font-bold leading-tight">
            Risk&nbsp;Assessment
          </span>
        )}
      </div>

      {/* Nav */}
      <nav className="flex-1 overflow-y-auto py-4 space-y-0.5 px-2">
        {NAV_ITEMS.filter((n) => n.group !== 'admin').map(({ id, label, icon: Icon }) => (
          <NavButton
            key={id}
            active={activeTab === id}
            collapsed={collapsed}
            label={label}
            Icon={Icon}
            onClick={() => onTabChange(id)}
          />
        ))}

        <div className="mt-4 pt-3 border-t border-sidebar-border">
          {!collapsed && (
            <p className="px-3 mb-1 text-[10px] uppercase tracking-wider text-sidebar-muted font-semibold">
              Admin
            </p>
          )}
          {NAV_ITEMS.filter((n) => n.group === 'admin').map(({ id, label, icon: Icon }) => (
            <NavButton
              key={id}
              active={activeTab === id}
              collapsed={collapsed}
              label={label}
              Icon={Icon}
              onClick={() => onTabChange(id)}
            />
          ))}
        </div>
      </nav>

      {/* Collapse toggle */}
      <button
        onClick={onToggle}
        className="flex h-10 items-center justify-center border-t border-sidebar-border hover:bg-white/5 transition-colors"
        aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
      >
        <ChevronLeft
          className={cn('h-4 w-4 text-sidebar-muted transition-transform', collapsed && 'rotate-180')}
        />
      </button>
    </aside>
  )
}

function NavButton({
  active, collapsed, label, Icon, onClick,
}: {
  active: boolean
  collapsed: boolean
  label: string
  Icon: React.ElementType
  onClick: () => void
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        'group relative w-full flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-all',
        active
          ? 'bg-sidebar-accent text-primary-foreground shadow-sm'
          : 'text-sidebar-muted hover:bg-white/5 hover:text-sidebar-foreground',
      )}
    >
      {active && (
        <span className="absolute left-0 top-1/2 h-5 -translate-y-1/2 w-1 rounded-r-full bg-primary-foreground/80" />
      )}
      <Icon className="h-[18px] w-[18px] shrink-0" />
      {!collapsed && <span className="truncate">{label}</span>}
    </button>
  )
}
