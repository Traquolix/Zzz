import { useState, useEffect, useMemo, useRef, useId } from 'react'
import { subDays, subWeeks, startOfDay, endOfDay, startOfWeek, endOfWeek, format } from 'date-fns'
import { Loader2, ChevronDown } from 'lucide-react'
import { fetchPeakFrequencies } from '@/api/infrastructure'
import type { PeakFrequencyData, SpectralSummary } from '@/types/infrastructure'

type ComparisonMode = 'day' | 'week' | 'custom'
type FocusMode = 'A' | 'equal' | 'B'

type TimeRange = { from: Date; to: Date }

type WindowData = {
    range: TimeRange
    data: PeakFrequencyData | null
    loading: boolean
}

function formatDateRange(range: TimeRange): string {
    const startDay = format(range.from, 'MMM d')
    const endDay = format(range.to, 'MMM d')
    return startDay === endDay ? startDay : `${startDay} – ${endDay}`
}

function getComparisonRanges(mode: ComparisonMode, dataEnd: Date): { a: TimeRange; b: TimeRange } {
    const latestDay = startOfDay(dataEnd)

    if (mode === 'day') {
        return {
            a: { from: latestDay, to: endOfDay(latestDay) },
            b: { from: subDays(latestDay, 1), to: endOfDay(subDays(latestDay, 1)) },
        }
    } else if (mode === 'week') {
        const thisWeekStart = startOfWeek(latestDay, { weekStartsOn: 1 })
        const thisWeekEnd = endOfWeek(latestDay, { weekStartsOn: 1 })
        const lastWeekStart = subWeeks(thisWeekStart, 1)
        const lastWeekEnd = subWeeks(thisWeekEnd, 1)
        return {
            a: { from: thisWeekStart, to: thisWeekEnd },
            b: { from: lastWeekStart, to: lastWeekEnd },
        }
    }
    // Custom - default to day over day
    return {
        a: { from: latestDay, to: endOfDay(latestDay) },
        b: { from: subDays(latestDay, 1), to: endOfDay(subDays(latestDay, 1)) },
    }
}

function ModeSelector({ mode, onChange }: { mode: ComparisonMode; onChange: (m: ComparisonMode) => void }) {
    const [isOpen, setIsOpen] = useState(false)

    const labels: Record<ComparisonMode, string> = {
        day: 'Day over day',
        week: 'Week over week',
        custom: 'Custom',
    }

    return (
        <div className="relative">
            <button
                onClick={() => setIsOpen(!isOpen)}
                className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium bg-slate-100 hover:bg-slate-200 rounded-md transition-colors"
            >
                {labels[mode]}
                <ChevronDown className="w-4 h-4" />
            </button>
            {isOpen && (
                <>
                    <div className="fixed inset-0 z-10" onClick={() => setIsOpen(false)} />
                    <div className="absolute top-full left-0 mt-1 bg-white border border-slate-200 rounded-md shadow-lg py-1 z-20 min-w-[140px]">
                        {(['day', 'week', 'custom'] as ComparisonMode[]).map((m) => (
                            <button
                                key={m}
                                onClick={() => { onChange(m); setIsOpen(false) }}
                                className={`block w-full text-left px-4 py-2 text-sm hover:bg-slate-50 ${
                                    mode === m ? 'bg-blue-50 text-blue-600' : 'text-slate-700'
                                }`}
                            >
                                {labels[m]}
                            </button>
                        ))}
                    </div>
                </>
            )}
        </div>
    )
}

function FocusToggle({ value, onChange }: { value: FocusMode; onChange: (f: FocusMode) => void }) {
    return (
        <div className="flex items-center bg-slate-100 rounded-md p-0.5">
            <button
                onClick={() => onChange('A')}
                className={`px-3 py-1 text-xs font-medium rounded transition-colors ${
                    value === 'A' ? 'bg-blue-500 text-white' : 'text-slate-500 hover:text-slate-700'
                }`}
            >
                A
            </button>
            <button
                onClick={() => onChange('equal')}
                className={`px-3 py-1 text-xs font-medium rounded transition-colors ${
                    value === 'equal' ? 'bg-slate-500 text-white' : 'text-slate-500 hover:text-slate-700'
                }`}
            >
                =
            </button>
            <button
                onClick={() => onChange('B')}
                className={`px-3 py-1 text-xs font-medium rounded transition-colors ${
                    value === 'B' ? 'bg-amber-500 text-white' : 'text-slate-500 hover:text-slate-700'
                }`}
            >
                B
            </button>
        </div>
    )
}

function OverlayScatter({
    dataA,
    dataB,
    focus,
    width,
}: {
    dataA: PeakFrequencyData | null
    dataB: PeakFrequencyData | null
    focus: FocusMode
    width: number
}) {
    const rawId = useId()
    const clipId = `overlay-scatter-clip-${rawId.replace(/:/g, '')}`
    const height = 160
    const padding = { top: 15, right: 15, bottom: 25, left: 45 }
    const plotWidth = Math.max(100, width - padding.left - padding.right)
    const plotHeight = height - padding.top - padding.bottom

    const freqMin = 1.05
    const freqMax = 1.20

    const yScale = (f: number) => padding.top + ((freqMax - f) / (freqMax - freqMin)) * plotHeight

    // Process points for both datasets - normalize X to 0-1 range so they overlay
    const processData = (data: PeakFrequencyData | null, color: string) => {
        if (!data || data.dt.length === 0) return []

        const duration = (data.dt[data.dt.length - 1] || 1) * 1000

        return data.dt.map((offsetSec, i) => {
            const normalizedX = (offsetSec * 1000) / duration
            const freq = data.peakFrequencies[i]
            const inRange = freq >= freqMin && freq <= freqMax
            return {
                x: padding.left + normalizedX * plotWidth,
                y: yScale(freq),
                freq,
                inRange,
                color,
            }
        })
    }

    const pointsA = processData(dataA, '#3b82f6')
    const pointsB = processData(dataB, '#f59e0b')

    // Determine opacity based on focus - harsh contrast for clear comparison
    const opacityA = focus === 'A' ? 0.7 : focus === 'equal' ? 0.3 : 0.04
    const opacityB = focus === 'B' ? 0.7 : focus === 'equal' ? 0.3 : 0.04

    const yTicks = [1.05, 1.10, 1.15, 1.20]

    return (
        <svg width="100%" height={height} viewBox={`0 0 ${width} ${height}`} className="overflow-visible" preserveAspectRatio="xMidYMid meet">
            <defs>
                <clipPath id={clipId}>
                    <rect x={padding.left} y={padding.top} width={plotWidth} height={plotHeight} />
                </clipPath>
            </defs>

            {/* Y-axis */}
            <line x1={padding.left} y1={padding.top} x2={padding.left} y2={height - padding.bottom} stroke="#e2e8f0" strokeWidth={1} />
            {yTicks.map((tick) => (
                <g key={tick}>
                    <line x1={padding.left - 4} y1={yScale(tick)} x2={padding.left} y2={yScale(tick)} stroke="#94a3b8" strokeWidth={1} />
                    <text x={padding.left - 8} y={yScale(tick)} textAnchor="end" dominantBaseline="middle" className="text-[10px] fill-slate-500">
                        {tick.toFixed(2)}
                    </text>
                </g>
            ))}
            <text x={12} y={height / 2} textAnchor="middle" dominantBaseline="middle" transform={`rotate(-90, 12, ${height / 2})`} className="text-[10px] fill-slate-500">
                Hz
            </text>

            {/* X-axis */}
            <line x1={padding.left} y1={height - padding.bottom} x2={width - padding.right} y2={height - padding.bottom} stroke="#e2e8f0" strokeWidth={1} />
            <text x={padding.left} y={height - 6} textAnchor="start" className="text-[9px] fill-slate-400">Start</text>
            <text x={width - padding.right} y={height - 6} textAnchor="end" className="text-[9px] fill-slate-400">End</text>

            {/* Data points - B behind, A in front when A focused, vice versa */}
            <g clipPath={`url(#${clipId})`}>
                {focus !== 'A' && pointsB.filter(pt => pt.inRange).map((pt, i) => (
                    <circle key={`b-${i}`} cx={pt.x} cy={pt.y} r={2.5} fill={pt.color} fillOpacity={opacityB} />
                ))}
                {pointsA.filter(pt => pt.inRange).map((pt, i) => (
                    <circle key={`a-${i}`} cx={pt.x} cy={pt.y} r={2.5} fill={pt.color} fillOpacity={opacityA} />
                ))}
                {focus === 'A' && pointsB.filter(pt => pt.inRange).map((pt, i) => (
                    <circle key={`b2-${i}`} cx={pt.x} cy={pt.y} r={2.5} fill={pt.color} fillOpacity={opacityB} />
                ))}
            </g>
        </svg>
    )
}

type Props = {
    dataSummary?: SpectralSummary | null
    selectedDay?: Date | null
}

export function TimeComparison({ dataSummary, selectedDay }: Props) {
    const containerRef = useRef<HTMLDivElement>(null)
    const [chartWidth, setChartWidth] = useState(400)
    const [mode, setMode] = useState<ComparisonMode>('day')
    const [focus, setFocus] = useState<FocusMode>('equal')

    // Reference date for comparisons: use selectedDay if provided, otherwise latest available
    const dataEndTimestamp = dataSummary?.endTime ?? null
    const selectedDayTimestamp = selectedDay?.getTime() ?? null
    const referenceDate = useMemo(() => {
        // If a specific day is selected, use end of that day as reference
        if (selectedDayTimestamp) {
            return endOfDay(new Date(selectedDayTimestamp))
        }
        // Otherwise use the latest available data
        return dataEndTimestamp ? new Date(dataEndTimestamp) : new Date()
    }, [selectedDayTimestamp, dataEndTimestamp])

    // Get ranges based on mode - memoize with stable dependencies
    const { rangeA, rangeB, labelA, labelB } = useMemo(() => {
        if (mode === 'custom' && customA && customB) {
            return {
                rangeA: customA,
                rangeB: customB,
                labelA: formatDateRange(customA),
                labelB: formatDateRange(customB),
            }
        }
        const ranges = getComparisonRanges(mode, referenceDate)
        return {
            rangeA: ranges.a,
            rangeB: ranges.b,
            labelA: formatDateRange(ranges.a),
            labelB: formatDateRange(ranges.b),
        }
    }, [mode, referenceDate, customA, customB])

    // Use stringified range as stable dependency for effects
    const rangeAKey = `${rangeA.from.getTime()}-${rangeA.to.getTime()}`
    const rangeBKey = `${rangeB.from.getTime()}-${rangeB.to.getTime()}`

    const [windowA, setWindowA] = useState<WindowData>({ range: rangeA, data: null, loading: false })
    const [windowB, setWindowB] = useState<WindowData>({ range: rangeB, data: null, loading: false })

    // Measure container width
    useEffect(() => {
        if (!containerRef.current) return
        const measure = () => {
            if (containerRef.current) {
                setChartWidth(Math.max(200, containerRef.current.clientWidth - 32))
            }
        }
        measure()
        const resizer = new ResizeObserver(measure)
        resizer.observe(containerRef.current)
        return () => resizer.disconnect()
    }, [])

    // Load data for window A
    useEffect(() => {
        async function load() {
            setWindowA(prev => ({ ...prev, range: rangeA, loading: true }))
            try {
                const data = await fetchPeakFrequencies({
                    maxSamples: 5000,
                    startTime: rangeA.from,
                    endTime: rangeA.to,
                })
                setWindowA(prev => ({ ...prev, data, loading: false }))
            } catch (err) {
                console.error('Failed to load window A data:', err)
                setWindowA(prev => ({ ...prev, data: null, loading: false }))
            }
        }
        load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [rangeAKey])

    // Load data for window B
    useEffect(() => {
        async function load() {
            setWindowB(prev => ({ ...prev, range: rangeB, loading: true }))
            try {
                const data = await fetchPeakFrequencies({
                    maxSamples: 5000,
                    startTime: rangeB.from,
                    endTime: rangeB.to,
                })
                setWindowB(prev => ({ ...prev, data, loading: false }))
            } catch (err) {
                console.error('Failed to load window B data:', err)
                setWindowB(prev => ({ ...prev, data: null, loading: false }))
            }
        }
        load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [rangeBKey])

    // Calculate stats
    const stats = useMemo(() => {
        const freqMin = 1.05
        const freqMax = 1.20

        const calcStats = (data: PeakFrequencyData | null) => {
            if (!data) return null
            const valid = data.peakFrequencies.filter(f => f >= freqMin && f <= freqMax)
            if (valid.length === 0) return null
            const mean = valid.reduce((a, b) => a + b, 0) / valid.length
            const variance = valid.reduce((sum, f) => sum + Math.pow(f - mean, 2), 0) / valid.length
            return { mean, std: Math.sqrt(variance), count: valid.length }
        }

        const a = calcStats(windowA.data)
        const b = calcStats(windowB.data)

        if (!a || !b) return null

        const diff = a.mean - b.mean
        const diffPercent = (diff / b.mean) * 100

        return { a, b, diff, diffPercent }
    }, [windowA.data, windowB.data])

    const isLoading = windowA.loading || windowB.loading

    return (
        <div className="bg-white rounded-lg border border-slate-200 p-5">
            {/* Header with mode selector */}
            <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-3">
                    <h3 className="text-base font-medium text-slate-900">Compare</h3>
                    <ModeSelector mode={mode} onChange={setMode} />
                </div>
                <FocusToggle value={focus} onChange={setFocus} />
            </div>

            {/* Period labels */}
            <div className="flex items-center gap-4 mb-4 text-sm">
                <div className="flex items-center gap-2">
                    <span className="w-3 h-3 rounded-full bg-blue-500" />
                    <span className="text-slate-600">A: {labelA}</span>
                </div>
                <span className="text-slate-300">vs</span>
                <div className="flex items-center gap-2">
                    <span className="w-3 h-3 rounded-full bg-amber-500" />
                    <span className="text-slate-600">B: {labelB}</span>
                </div>
            </div>

            {/* Overlay chart */}
            <div ref={containerRef} className="bg-slate-50 rounded-lg p-4">
                {isLoading ? (
                    <div className="flex items-center justify-center h-[160px]">
                        <Loader2 className="w-5 h-5 animate-spin text-slate-400" />
                    </div>
                ) : (
                    <OverlayScatter
                        dataA={windowA.data}
                        dataB={windowB.data}
                        focus={focus}
                        width={chartWidth}
                    />
                )}
            </div>

            {/* Stats */}
            {stats && (
                <div className="mt-4 space-y-2">
                    {/* Frequency shift - prominent */}
                    <div className="flex items-center justify-center gap-2 py-2 bg-slate-50 rounded-lg">
                        <span className="text-sm text-slate-600">Frequency shift:</span>
                        <span className={`text-lg font-semibold ${
                            stats.diff > 0 ? 'text-green-600' : stats.diff < 0 ? 'text-red-600' : 'text-slate-600'
                        }`}>
                            {stats.diff > 0 ? '+' : ''}{(stats.diff * 1000).toFixed(2)} mHz
                        </span>
                        <span className={`text-sm ${
                            stats.diff > 0 ? 'text-green-500' : stats.diff < 0 ? 'text-red-500' : 'text-slate-400'
                        }`}>
                            ({stats.diffPercent > 0 ? '+' : ''}{stats.diffPercent.toFixed(2)}%)
                        </span>
                    </div>

                    {/* Individual stats */}
                    <div className="grid grid-cols-2 gap-4 text-xs">
                        <div className="flex items-center gap-2">
                            <span className="w-2 h-2 rounded-full bg-blue-500" />
                            <span className="text-slate-500">Mean:</span>
                            <span className="font-medium text-slate-700">{stats.a.mean.toFixed(4)} Hz</span>
                            <span className="text-slate-400">(σ={stats.a.std.toFixed(4)})</span>
                        </div>
                        <div className="flex items-center gap-2">
                            <span className="w-2 h-2 rounded-full bg-amber-500" />
                            <span className="text-slate-500">Mean:</span>
                            <span className="font-medium text-slate-700">{stats.b.mean.toFixed(4)} Hz</span>
                            <span className="text-slate-400">(σ={stats.b.std.toFixed(4)})</span>
                        </div>
                    </div>
                </div>
            )}
        </div>
    )
}
