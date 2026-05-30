import { useState } from 'react'
import { Sidebar, type TabId } from './Sidebar'
import { Header } from './Header'
import { FreshnessFooter } from './FreshnessFooter'

interface LayoutProps {
  activeTab: TabId
  onTabChange: (tab: TabId) => void
  children: React.ReactNode
}

export function Layout({ activeTab, onTabChange, children }: LayoutProps) {
  const [collapsed, setCollapsed] = useState(false)
  const sidebarWidth = collapsed ? 64 : 224

  return (
    <div className="min-h-screen bg-background text-foreground">
      <Sidebar
        activeTab={activeTab}
        onTabChange={onTabChange}
        collapsed={collapsed}
        onToggle={() => setCollapsed((c) => !c)}
      />
      <Header sidebarWidth={sidebarWidth} />
      <main
        className="pt-16 pb-10 transition-all duration-200 min-h-screen"
        style={{ marginLeft: sidebarWidth }}
      >
        <div className="p-6">{children}</div>
      </main>
      <FreshnessFooter sidebarWidth={sidebarWidth} />
    </div>
  )
}
