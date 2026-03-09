import { useState, lazy, Suspense } from 'react'
import { cn } from '@/lib/utils'
import type { TimeSeriesPoint } from '../types'
import { chartColors } from '../data'

const LazyChart = lazy(() => import('./TimeSeriesChartInner'))

interface TimeSeriesChartProps {
  data: TimeSeriesPoint[]
  timeRange?: string
  incidentTime?: string // "HH:MM:SS" — renders a vertical marker on all charts
}

type MetricKey = 'speed' | 'flow' | 'occupancy'

export function TimeSeriesChart({ data, timeRange, incidentTime }: TimeSeriesChartProps) {
  const [metric, setMetric] = useState<MetricKey>('speed')

  return (
    <div>
      <div className="flex gap-1.5 mb-3">
        {(Object.keys(chartColors) as MetricKey[]).map(key => (
          <button
            key={key}
            onClick={() => setMetric(key)}
            className={cn(
              'px-2.5 py-1 rounded text-xs transition-colors cursor-pointer',
              metric === key
                ? 'bg-[var(--proto-accent)] text-white'
                : 'bg-[var(--proto-surface)] text-[var(--proto-text-secondary)] hover:text-[var(--proto-text)]',
            )}
          >
            {chartColors[key].label}
          </button>
        ))}
      </div>

      {data.length === 0 ? (
        <div className="h-[200px] flex items-center justify-center text-[var(--proto-text-muted)] text-xs">
          No data available
        </div>
      ) : (
        <Suspense
          fallback={
            <div className="h-[200px] flex items-center justify-center text-[var(--proto-text-muted)] text-xs">
              Loading chart...
            </div>
          }
        >
          <LazyChart
            data={data}
            metric={metric}
            config={chartColors[metric]}
            timeRange={timeRange}
            incidentTime={incidentTime}
          />
        </Suspense>
      )}
    </div>
  )
}
