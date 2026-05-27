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
        'fixed inset-y-0 left-0 z-40 flex flex-col bg-slate-900 text-slate-300 transition-all duration-200',
        collapsed ? 'w-16' : 'w-56',
      )}
    >
      {/* Logo */}
      <div className="flex h-16 items-center gap-3 px-4 border-b border-slate-800">
        <ShieldAlert className="h-7 w-7 text-brand-500 shrink-0" />
        {!collapsed && (
          <span className="text-sm font-bold text-white leading-tight">
            Risk&nbsp;Assessment
          </span>
        )}
      </div>

      {/* Nav */}
      <nav className="flex-1 overflow-y-auto py-4 space-y-0.5 px-2">
        {NAV_ITEMS.filter((n) => n.group !== 'admin').map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => onTabChange(id)}
            className={cn(
              'w-full flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors',
              activeTab === id
                ? 'bg-brand-600 text-white'
                : 'text-slate-400 hover:bg-slate-800 hover:text-white',
            )}
          >
            <Icon className="h-4.5 w-4.5 shrink-0 h-[18px] w-[18px]" />
            {!collapsed && <span className="truncate">{label}</span>}
          </button>
        ))}

        {/* Admin section divider */}
        <div className="mt-4 pt-3 border-t border-slate-800">
          {!collapsed && (
            <p className="px-3 mb-1 text-[10px] uppercase tracking-wider text-slate-500 font-semibold">
              Admin
            </p>
          )}
          {NAV_ITEMS.filter((n) => n.group === 'admin').map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              onClick={() => onTabChange(id)}
              className={cn(
                'w-full flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors',
                activeTab === id
                  ? 'bg-slate-700 text-white'
                  : 'text-slate-500 hover:bg-slate-800 hover:text-slate-200',
              )}
            >
              <Icon className="h-4.5 w-4.5 shrink-0 h-[18px] w-[18px]" />
              {!collapsed && <span className="truncate">{label}</span>}
            </button>
          ))}
        </div>
      </nav>

      {/* Collapse toggle */}
      <button
        onClick={onToggle}
        className="flex h-10 items-center justify-center border-t border-slate-800 hover:bg-slate-800 transition-colors"
        aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
      >
        <ChevronLeft
          className={cn('h-4 w-4 text-slate-400 transition-transform', collapsed && 'rotate-180')}
        />
      </button>
    </aside>
  )
}
