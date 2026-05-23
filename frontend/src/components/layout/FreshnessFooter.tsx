import { formatDistanceToNow } from 'date-fns'
import { useFreshness } from '@/api/hooks'
import { cn } from '@/lib/utils'

interface Props {
  sidebarWidth: number
}

export function FreshnessFooter({ sidebarWidth }: Props) {
  const { data } = useFreshness()

  const pipelineAt = data?.last_pipeline_run_at
    ? formatDistanceToNow(new Date(data.last_pipeline_run_at), { addSuffix: true })
    : null

  const dataAt = data?.latest_data_date

  const statusOk = data?.pipeline_run_status === 'success'

  return (
    <footer
      className="fixed bottom-0 right-0 z-30 flex h-8 items-center gap-4 border-t border-slate-200 bg-slate-50 px-6 text-xs text-slate-400 transition-all duration-200"
      style={{ left: sidebarWidth }}
    >
      {pipelineAt && (
        <span className="flex items-center gap-1.5">
          <span
            className={cn('h-1.5 w-1.5 rounded-full', statusOk ? 'bg-green-400' : 'bg-amber-400')}
          />
          Pipeline last ran {pipelineAt}
        </span>
      )}
      {dataAt && <span>Data through {dataAt}</span>}
      {data?.latest_predicted_quarter && (
        <span>Forecast through {data.latest_predicted_quarter}</span>
      )}
    </footer>
  )
}
