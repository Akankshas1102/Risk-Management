import { FileText, Download, BarChart2, Calendar } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'

const REPORT_TYPES = [
  {
    icon: BarChart2,
    title: 'Quarterly Risk Report',
    desc: 'Comprehensive PDF/XLSX with all risk metrics, drivers, and recommendations.',
    badge: 'Coming soon',
  },
  {
    icon: Calendar,
    title: 'Monthly Trend Report',
    desc: 'Monthly incident volume, category breakdown, and YoY comparison.',
    badge: 'Coming soon',
  },
  {
    icon: FileText,
    title: 'Site Comparison Report',
    desc: 'Cross-site benchmarking for business-unit leadership.',
    badge: 'Coming soon',
  },
  {
    icon: Download,
    title: 'Raw Data Export',
    desc: 'CSV export of filtered incidents_clean and risk scores for offline analysis.',
    badge: 'Coming soon',
  },
]

export function Reports() {
  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <div className="h-10 w-10 rounded-xl bg-slate-100 flex items-center justify-center">
          <FileText className="h-5 w-5 text-slate-600" />
        </div>
        <div>
          <h2 className="text-lg font-bold text-slate-800">Reports</h2>
          <p className="text-sm text-slate-500">Scheduled and on-demand report generation — coming soon</p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {REPORT_TYPES.map(({ icon: Icon, title, desc, badge }, i) => (
          <Card key={i} className="flex items-start gap-4 p-5">
            <div className="h-10 w-10 rounded-lg bg-slate-100 flex items-center justify-center shrink-0">
              <Icon className="h-5 w-5 text-slate-500" />
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center justify-between gap-2">
                <p className="text-sm font-semibold text-slate-800">{title}</p>
                <span className="text-xs text-slate-400 bg-slate-100 rounded-full px-2 py-0.5 shrink-0">
                  {badge}
                </span>
              </div>
              <p className="text-sm text-slate-500 mt-1">{desc}</p>
              <Button variant="outline" size="sm" className="mt-3 opacity-50 cursor-not-allowed" disabled>
                <Download className="h-3.5 w-3.5 mr-1.5" /> Generate
              </Button>
            </div>
          </Card>
        ))}
      </div>
    </div>
  )
}
