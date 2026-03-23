import { useRef, useState, useEffect } from 'react'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ReferenceLine } from 'recharts'
import type { TimeSeriesPoint } from '../types'
import { useDebouncedResize } from '../hooks/useDebouncedResize'
import { COLORS } from '@/lib/theme'

interface Props {
  data: TimeSeriesPoint[]
  metric: 'speed' | 'flow' | 'occupancy'
  config: { label: string; unit: string; color: string }
  timeRange?: string
  incidentTime?: string
}

export default function TimeSeriesChartInner({ data, metric, config, timeRange, incidentTime }: Props) {
  const stripSeconds = timeRange === '15m' || timeRange === '1h'
  const tickFormatter = stripSeconds
    ? (value: string) => value?.slice(0, 5) // "HH:MM:SS" → "HH:MM"
    : undefined

  const containerRef = useRef<HTMLDivElement>(null)
  const { width, transitioning } = useDebouncedResize(containerRef)

  // Defer rendering until the container has positive dimensions to prevent
  // Recharts "width(-1) height(-1)" warnings on hidden/collapsed panels
  const [visible, setVisible] = useState(false)
  useEffect(() => {
    if (width > 0) setVisible(true)
  }, [width])

  const chartHeight = 200

  return (
    <div ref={containerRef} className="h-[200px]">
      {!visible || transitioning ? (
        <ChartSkeleton />
      ) : (
        width > 0 && (
          <LineChart data={data} width={width} height={chartHeight} margin={{ top: 4, right: 4, bottom: 4, left: 4 }}>
            <CartesianGrid stroke="var(--proto-chart-grid, rgba(255,255,255,0.03))" strokeDasharray="3 3" />
            <XAxis
              dataKey="time"
              tick={{ fill: COLORS.timeSeries.tickFill, fontSize: 10 }}
              tickLine={false}
              axisLine={false}
              interval={Math.max(0, Math.floor(data.length / 6) - 1)}
              tickFormatter={tickFormatter}
            />
            <YAxis
              tick={{ fill: COLORS.timeSeries.tickFill, fontSize: 10 }}
              tickLine={false}
              axisLine={false}
              width={36}
              domain={[0, (max: number) => Math.ceil(max * 1.1)]}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: COLORS.timeSeries.tooltipBg,
                border: `1px solid ${COLORS.timeSeries.tooltipBorder}`,
                borderRadius: 8,
                fontSize: 12,
                color: COLORS.timeSeries.tooltipText,
                boxShadow: '0 4px 12px rgba(0,0,0,0.3)',
              }}
              formatter={(value: number | undefined) => [`${value ?? 0} ${config.unit}`, config.label]}
            />
            {incidentTime && (
              <ReferenceLine
                x={incidentTime}
                stroke="var(--proto-red, #ef4444)"
                strokeDasharray="4 3"
                strokeWidth={1.5}
                label={{ value: 'Incident', position: 'top', fill: 'var(--proto-red, #ef4444)', fontSize: 9 }}
              />
            )}
            <Line
              type="monotone"
              dataKey={metric}
              stroke={config.color}
              strokeWidth={1.5}
              dot={false}
              activeDot={{ r: 2.5, fill: config.color }}
              connectNulls
              isAnimationActive={false}
            />
          </LineChart>
        )
      )}
    </div>
  )
}

function ChartSkeleton() {
  return <div className="w-full h-full rounded-lg bg-[var(--proto-surface-raised)] animate-pulse" />
}
