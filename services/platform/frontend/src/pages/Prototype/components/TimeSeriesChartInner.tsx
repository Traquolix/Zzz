import {
    LineChart,
    Line,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    ResponsiveContainer,
} from 'recharts'
import type { TimeSeriesPoint } from '../types'

interface Props {
    data: TimeSeriesPoint[]
    metric: 'speed' | 'flow' | 'occupancy'
    config: { label: string; unit: string; color: string }
    timeRange?: string
}

export default function TimeSeriesChartInner({ data, metric, config, timeRange }: Props) {
    const stripSeconds = timeRange === '15m' || timeRange === '1h'
    const tickFormatter = stripSeconds
        ? (value: string) => value?.slice(0, 5) // "HH:MM:SS" → "HH:MM"
        : undefined
    return (
        <div className="h-[200px]">
            <ResponsiveContainer width="100%" height="100%">
                <LineChart data={data} margin={{ top: 4, right: 4, bottom: 4, left: 4 }}>
                    <CartesianGrid stroke="var(--proto-chart-grid, rgba(255,255,255,0.03))" strokeDasharray="3 3" />
                    <XAxis
                        dataKey="time"
                        tick={{ fill: '#64748b', fontSize: 10 }}
                        tickLine={false}
                        axisLine={false}
                        interval={Math.max(0, Math.floor(data.length / 6) - 1)}
                        tickFormatter={tickFormatter}
                    />
                    <YAxis
                        tick={{ fill: '#64748b', fontSize: 10 }}
                        tickLine={false}
                        axisLine={false}
                        width={36}
                    />
                    <Tooltip
                        contentStyle={{
                            backgroundColor: '#2b2d31',
                            border: '1px solid rgba(255,255,255,0.08)',
                            borderRadius: 8,
                            fontSize: 12,
                            color: '#e2e8f0',
                            boxShadow: '0 4px 12px rgba(0,0,0,0.3)',
                        }}
                        formatter={(value: number | undefined) => [`${value ?? 0} ${config.unit}`, config.label]}
                    />
                    <Line
                        type="monotone"
                        dataKey={metric}
                        stroke={config.color}
                        strokeWidth={1.5}
                        dot={false}
                        activeDot={{ r: 2.5, fill: config.color }}
                        isAnimationActive={false}
                    />
                </LineChart>
            </ResponsiveContainer>
        </div>
    )
}
