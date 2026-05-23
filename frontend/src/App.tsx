import { useState } from 'react'
import { Layout } from '@/components/layout/Layout'
import { type TabId } from '@/components/layout/Sidebar'
import { Overview }           from '@/tabs/Overview'
import { RiskDrivers }        from '@/tabs/RiskDrivers'
import { IncidentBreakdown }  from '@/tabs/IncidentBreakdown'
import { Trends }             from '@/tabs/Trends'
import { Predictions }        from '@/tabs/Predictions'
import { Recommendations }    from '@/tabs/Recommendations'
import { AIInsights }         from '@/tabs/AIInsights'
import { Reports }            from '@/tabs/Reports'

const TAB_COMPONENTS: Record<TabId, React.ComponentType> = {
  'overview':           Overview,
  'risk-drivers':       RiskDrivers,
  'incident-breakdown': IncidentBreakdown,
  'trends':             Trends,
  'predictions':        Predictions,
  'recommendations':    Recommendations,
  'ai-insights':        AIInsights,
  'reports':            Reports,
}

export default function App() {
  const [activeTab, setActiveTab] = useState<TabId>('overview')
  const ActiveComponent = TAB_COMPONENTS[activeTab]

  return (
    <Layout activeTab={activeTab} onTabChange={setActiveTab}>
      <ActiveComponent />
    </Layout>
  )
}
