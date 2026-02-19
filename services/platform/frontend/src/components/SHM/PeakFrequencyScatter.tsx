import { useMemo, useState, useRef, useCallback, useId } from 'react'
import { RotateCcw } from 'lucide-react'
import type { PeakFrequencyData } from '@/types/infrastructure'

type Props = {
    data: PeakFrequencyData
    width?: number
    height?: number
}

type TooltipState = {
    x: number
    y: number
    freq: number
    power: number
    timestamp: Date
} | null

type BrushState = {
    startX: number
    currentX: number
} | null

type ZoomRange = {
    startMs: number
    endMs: number
} | null

/**
 * Format hour for X-axis label (24h format).
 */
function formatHourLabel(date: Date): string {
    return `${date.getHours().toString().padStart(2, '0')}:00`
}

/**
 * Format timestamp for tooltip.
 */
function formatTimestamp(date: Date): string {
    return date.toLocaleString(undefined, {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
    })
}

export function PeakFrequencyScatter({ data, width = 800, height = 200 }: Props) {
    const [tooltip, setTooltip] = useState<TooltipState>(null)
    const [brush, setBrush] = useState<BrushState>(null)
    const [zoom, setZoom] = useState<ZoomRange>(null)
    const svgRef = useRef<SVGSVGElement>(null)
    const rawId = useId()
    const clipId = `scatter-clip-${rawId.replace(/:/g, '')}`

    const padding = { top: 20, right: 20, bottom: 30, left: 50 }
    const plotWidth = width - padding.left - padding.right
    const plotHeight = height - padding.top - padding.bottom

    // Parse start time
    const t0 = useMemo(() => new Date(data.t0), [data.t0])

    // Full data time range
    const fullTimeRange = useMemo(() => {
        const min = t0.getTime()
        const max = min + (data.dt[data.dt.length - 1] || 0) * 1000
        return { min, max }
    }, [t0, data.dt])

    // Effective time range (considering zoom)
    const timeRange = useMemo(() => {
        if (zoom) {
            return { min: zoom.startMs, max: zoom.endMs }
        }
        return fullTimeRange
    }, [zoom, fullTimeRange])

    // Compute scales and data points
    const { points, xScale, yScale, freqMin, freqMax, inverseXScale } = useMemo(() => {
        // Fixed frequency range per Martijn's instructions
        const freqMin = 1.05
        const freqMax = 1.20

        // Calculate power range for sizing
        let pMin = Infinity
        let pMax = -Infinity
        for (const p of data.peakPowers) {
            if (p < pMin) pMin = p
            if (p > pMax) pMax = p
        }

        const { min: timeMin, max: timeMax } = timeRange

        const xScale = (ms: number) => padding.left + ((ms - timeMin) / (timeMax - timeMin)) * plotWidth
        const yScale = (f: number) => padding.top + ((freqMax - f) / (freqMax - freqMin)) * plotHeight
        const inverseXScale = (px: number) => timeMin + ((px - padding.left) / plotWidth) * (timeMax - timeMin)

        // Map points with actual timestamps
        const pts = data.dt.map((offsetSec, i) => {
            const timestamp = new Date(t0.getTime() + offsetSec * 1000)
            const ms = timestamp.getTime()
            const freq = data.peakFrequencies[i]
            const inRange = freq >= freqMin && freq <= freqMax
            const inTimeRange = ms >= timeMin && ms <= timeMax
            return {
                x: xScale(ms),
                y: yScale(freq),
                freq,
                power: data.peakPowers[i],
                timestamp,
                size: 2 + ((data.peakPowers[i] - pMin) / (pMax - pMin + 1e-10)) * 4,
                inRange,
                inTimeRange,
            }
        })

        return { points: pts, xScale, yScale, freqMin, freqMax, inverseXScale }
    }, [data, t0, plotWidth, plotHeight, padding.left, padding.top, timeRange])

    // Generate Y-axis ticks
    const yTicks = useMemo(() => {
        const tickCount = 5
        const step = (freqMax - freqMin) / (tickCount - 1)
        return Array.from({ length: tickCount }, (_, i) => freqMin + i * step)
    }, [freqMin, freqMax])

    // Generate X-axis ticks at meaningful hour boundaries
    const xTicks = useMemo(() => {
        const ticks: { x: number; label: string }[] = []
        const { min: timeMin, max: timeMax } = timeRange
        const durationHours = (timeMax - timeMin) / (1000 * 3600)

        // Determine tick interval based on duration
        let hourInterval = 1
        if (durationHours > 72) hourInterval = 12
        else if (durationHours > 24) hourInterval = 6
        else if (durationHours > 12) hourInterval = 3
        else if (durationHours > 6) hourInterval = 2

        // Start from the next round hour
        let current = new Date(timeMin)
        current.setMinutes(0, 0, 0)
        if (current.getTime() < timeMin) {
            current.setHours(current.getHours() + 1)
        }

        // Align to interval
        const startHour = current.getHours()
        const alignedHour = Math.ceil(startHour / hourInterval) * hourInterval
        current.setHours(alignedHour)

        while (current.getTime() <= timeMax) {
            if (current.getTime() >= timeMin) {
                ticks.push({
                    x: xScale(current.getTime()),
                    label: formatHourLabel(current),
                })
            }
            current.setHours(current.getHours() + hourInterval)
        }

        return ticks
    }, [timeRange, xScale])

    // Brush handlers
    const getMouseX = useCallback((e: React.MouseEvent) => {
        if (!svgRef.current) return 0
        const rect = svgRef.current.getBoundingClientRect()
        return e.clientX - rect.left
    }, [])

    const handleMouseDown = useCallback((e: React.MouseEvent) => {
        const x = getMouseX(e)
        // Only start brush if within plot area
        if (x >= padding.left && x <= width - padding.right) {
            setBrush({ startX: x, currentX: x })
            setTooltip(null)
        }
    }, [getMouseX, padding.left, width, padding.right])

    const handleMouseMove = useCallback((e: React.MouseEvent) => {
        if (brush) {
            const x = Math.max(padding.left, Math.min(width - padding.right, getMouseX(e)))
            setBrush({ ...brush, currentX: x })
        }
    }, [brush, getMouseX, padding.left, width, padding.right])

    const handleMouseUp = useCallback(() => {
        if (brush) {
            const minX = Math.min(brush.startX, brush.currentX)
            const maxX = Math.max(brush.startX, brush.currentX)

            // Only zoom if selection is at least 10px wide
            if (maxX - minX > 10) {
                const startMs = inverseXScale(minX)
                const endMs = inverseXScale(maxX)
                setZoom({ startMs, endMs })
            }

            setBrush(null)
        }
    }, [brush, inverseXScale])

    const handleMouseLeave = useCallback(() => {
        if (brush) {
            setBrush(null)
        }
    }, [brush])

    const handleDoubleClick = useCallback(() => {
        setZoom(null)
    }, [])

    const handleResetZoom = useCallback(() => {
        setZoom(null)
    }, [])

    // Brush rectangle bounds
    const brushRect = brush ? {
        x: Math.min(brush.startX, brush.currentX),
        width: Math.abs(brush.currentX - brush.startX),
    } : null

    return (
        <div className="relative">
            {/* Reset zoom button */}
            {zoom && (
                <button
                    onClick={handleResetZoom}
                    className="absolute top-0 right-0 flex items-center gap-1 px-2 py-1 text-xs text-slate-500 hover:text-slate-700 hover:bg-slate-100 rounded transition-colors z-10"
                >
                    <RotateCcw className="w-3 h-3" />
                    Reset zoom
                </button>
            )}

            {/* SVG wrapper with overflow hidden to clip points */}
            <div className="overflow-hidden">
                <svg
                    ref={svgRef}
                    width="100%"
                    height={height}
                    viewBox={`0 0 ${width} ${height}`}
                    preserveAspectRatio="xMidYMid meet"
                    className="select-none"
                    onMouseDown={handleMouseDown}
                    onMouseMove={handleMouseMove}
                    onMouseUp={handleMouseUp}
                    onMouseLeave={handleMouseLeave}
                    onDoubleClick={handleDoubleClick}
                >
                {/* Clip path for plot area */}
                <defs>
                    <clipPath id={clipId}>
                        <rect
                            x={padding.left}
                            y={padding.top}
                            width={plotWidth}
                            height={plotHeight}
                        />
                    </clipPath>
                </defs>

                {/* Y-axis */}
                <line
                    x1={padding.left}
                    y1={padding.top}
                    x2={padding.left}
                    y2={height - padding.bottom}
                    stroke="#e2e8f0"
                    strokeWidth={1}
                />
                {yTicks.map((tick) => (
                    <g key={tick}>
                        <line
                            x1={padding.left - 4}
                            y1={yScale(tick)}
                            x2={padding.left}
                            y2={yScale(tick)}
                            stroke="#94a3b8"
                            strokeWidth={1}
                        />
                        <text
                            x={padding.left - 8}
                            y={yScale(tick)}
                            textAnchor="end"
                            dominantBaseline="middle"
                            className="text-[10px] fill-slate-500"
                        >
                            {tick.toFixed(2)}
                        </text>
                    </g>
                ))}
                <text
                    x={15}
                    y={height / 2}
                    textAnchor="middle"
                    dominantBaseline="middle"
                    transform={`rotate(-90, 15, ${height / 2})`}
                    className="text-[10px] fill-slate-500"
                >
                    Peak Freq (Hz)
                </text>

                {/* X-axis */}
                <line
                    x1={padding.left}
                    y1={height - padding.bottom}
                    x2={width - padding.right}
                    y2={height - padding.bottom}
                    stroke="#e2e8f0"
                    strokeWidth={1}
                />
                {xTicks.map((tick, i) => (
                    <g key={i}>
                        <line
                            x1={tick.x}
                            y1={height - padding.bottom}
                            x2={tick.x}
                            y2={height - padding.bottom + 4}
                            stroke="#94a3b8"
                            strokeWidth={1}
                        />
                        <text
                            x={tick.x}
                            y={height - padding.bottom + 14}
                            textAnchor="middle"
                            className="text-[10px] fill-slate-500"
                        >
                            {tick.label}
                        </text>
                    </g>
                ))}
                <text
                    x={width / 2}
                    y={height - 5}
                    textAnchor="middle"
                    className="text-[10px] fill-slate-500"
                >
                    Time (hour) {zoom ? '- drag to zoom, double-click to reset' : '- drag to zoom'}
                </text>

                {/* Data points - clipped to plot area */}
                <g clipPath={`url(#${clipId})`}>
                    {points.filter(pt => pt.inRange && pt.inTimeRange).map((pt, i) => (
                        <circle
                            key={i}
                            cx={pt.x}
                            cy={pt.y}
                            r={pt.size}
                            fill="#f59e0b"
                            fillOpacity={0.1}
                            stroke="none"
                            className="cursor-crosshair hover:fill-opacity-60"
                            onMouseEnter={(e) => {
                                e.stopPropagation()
                                if (!brush) {
                                    setTooltip({ x: pt.x, y: pt.y, freq: pt.freq, power: pt.power, timestamp: pt.timestamp })
                                }
                            }}
                            onMouseLeave={() => setTooltip(null)}
                        />
                    ))}
                </g>

                {/* Brush selection rectangle */}
                {brushRect && (
                    <rect
                        x={brushRect.x}
                        y={padding.top}
                        width={brushRect.width}
                        height={plotHeight}
                        fill="#3b82f6"
                        fillOpacity={0.2}
                        stroke="#3b82f6"
                        strokeWidth={1}
                        pointerEvents="none"
                    />
                )}
                </svg>
            </div>

            {/* Tooltip - outside overflow-hidden wrapper */}
            {tooltip && !brush && (() => {
                // Flip tooltip to left side when point is in right half of chart
                const isRightSide = tooltip.x > width * 0.6
                return (
                    <div
                        className="absolute bg-slate-800 text-white text-xs px-2 py-1 rounded shadow-lg pointer-events-none z-10 whitespace-nowrap"
                        style={{
                            left: isRightSide ? undefined : tooltip.x + 10,
                            right: isRightSide ? width - tooltip.x + 10 : undefined,
                            top: tooltip.y - 10,
                            transform: 'translateY(-100%)',
                        }}
                    >
                        <div>Freq: {tooltip.freq.toFixed(3)} Hz</div>
                        <div>Power: {tooltip.power.toFixed(2)}</div>
                        <div>{formatTimestamp(tooltip.timestamp)}</div>
                    </div>
                )
            })()}
        </div>
    )
}
