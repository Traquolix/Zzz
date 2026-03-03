import { useEffect, useRef, useState, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import type { SelectedInfrastructure, FrequencyReading } from '@/types/infrastructure'
import type { FrequencyDataPoint, TimeRange } from './SHMWidget'
import { COLORS } from '@/lib/theme'
import {
    setupCanvas,
    getChartDimensions,
    drawBackground,
    drawAxes,
    type ChartPadding
} from '@/lib/chartUtils'

const CHART_PADDING: ChartPadding = { top: 24, right: 16, bottom: 28, left: 44 }

type Props = {
    infrastructure: SelectedInfrastructure
    latestReading: FrequencyReading | null
    historyData: FrequencyDataPoint[]
    comparisonData: FrequencyDataPoint[]
    timeRange: TimeRange
    showComparison: boolean
    now: number
}

type HoveredPoint = {
    x: number
    y: number
    point: FrequencyDataPoint
    isComparison: boolean
} | null

export function InfrastructureDetail({
    infrastructure,
    latestReading,
    historyData,
    comparisonData,
    timeRange,
    showComparison,
    now
}: Props) {
    const { t } = useTranslation()
    const canvasRef = useRef<HTMLCanvasElement>(null)
    const containerRef = useRef<HTMLDivElement>(null)
    const [hoveredPoint, setHoveredPoint] = useState<HoveredPoint>(null)

    // Store chart dimensions for mouse handling
    const chartStateRef = useRef<{
        minTime: number
        timeWindowMs: number
        minFreq: number
        freqRange: number
        dims: ReturnType<typeof getChartDimensions> | null
    }>({ minTime: 0, timeWindowMs: 0, minFreq: 0, freqRange: 0, dims: null })

    const timeWindowMs = timeRange.ms

    // Find nearest point to mouse position
    const findNearestPoint = useCallback((mouseX: number, mouseY: number): HoveredPoint => {
        const state = chartStateRef.current
        if (!state.dims || historyData.length === 0) return null

        const { dims, minTime, timeWindowMs: twMs, minFreq, freqRange } = state

        // Convert mouse position to chart coordinates
        const chartX = mouseX - dims.padding.left
        const chartY = mouseY - dims.padding.top

        // Check if within chart area
        if (chartX < 0 || chartX > dims.chartWidth || chartY < 0 || chartY > dims.chartHeight) {
            return null
        }

        // Helper to calculate distance
        const getDistance = (point: FrequencyDataPoint) => {
            const px = ((point.timestamp - minTime) / twMs) * dims.chartWidth
            const py = dims.chartHeight - ((point.frequency - minFreq) / freqRange) * dims.chartHeight
            return Math.hypot(chartX - px, chartY - py)
        }

        // Find nearest in main data
        let nearest: FrequencyDataPoint | null = null
        let nearestDist = Infinity
        let isComparison = false

        for (const point of historyData) {
            const dist = getDistance(point)
            if (dist < nearestDist && dist < 30) {
                nearestDist = dist
                nearest = point
                isComparison = false
            }
        }

        // Check comparison data if enabled
        if (showComparison && comparisonData.length > 0) {
            for (const point of comparisonData) {
                const dist = getDistance(point)
                if (dist < nearestDist && dist < 30) {
                    nearestDist = dist
                    nearest = point
                    isComparison = true
                }
            }
        }

        if (!nearest) return null

        // Calculate screen position for tooltip
        const px = dims.padding.left + ((nearest.timestamp - minTime) / twMs) * dims.chartWidth
        const py = dims.padding.top + dims.chartHeight - ((nearest.frequency - minFreq) / freqRange) * dims.chartHeight

        return { x: px, y: py, point: nearest, isComparison }
    }, [historyData, comparisonData, showComparison])

    // Mouse move handler
    const handleMouseMove = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
        const canvas = canvasRef.current
        if (!canvas) return

        const rect = canvas.getBoundingClientRect()
        const mouseX = e.clientX - rect.left
        const mouseY = e.clientY - rect.top

        setHoveredPoint(findNearestPoint(mouseX, mouseY))
    }, [findNearestPoint])

    const handleMouseLeave = useCallback(() => {
        setHoveredPoint(null)
    }, [])

    // Draw the frequency chart
    useEffect(() => {
        const canvas = canvasRef.current
        if (!canvas) return

        const setup = setupCanvas(canvas)
        if (!setup) return

        const { ctx, width, height } = setup
        const dims = getChartDimensions(width, height, CHART_PADDING)

        // Clear and draw background
        ctx.clearRect(0, 0, width, height)
        drawBackground(ctx, width, height)

        // Draw title
        ctx.font = '11px system-ui, -apple-system, sans-serif'
        ctx.fillStyle = COLORS.canvas.axis
        ctx.textAlign = 'left'
        ctx.fillText(t('shm.frequencyHz'), dims.padding.left, 14)

        // If no data, show message
        if (historyData.length === 0) {
            ctx.font = '13px system-ui, -apple-system, sans-serif'
            ctx.fillStyle = COLORS.canvas.label
            ctx.textAlign = 'center'
            ctx.textBaseline = 'middle'
            ctx.fillText(t('shm.waitingForData'), width / 2, height / 2)
            chartStateRef.current.dims = null
            return
        }

        // Calculate Y range from both datasets
        const allFrequencies = [
            ...historyData.map(p => p.frequency),
            ...(showComparison ? comparisonData.map(p => p.frequency) : [])
        ]
        const minFreq = Math.floor(Math.min(...allFrequencies) - 0.5)
        const maxFreq = Math.ceil(Math.max(...allFrequencies) + 0.5)
        const freqRange = Math.max(maxFreq - minFreq, 1)

        // Time range
        const minTime = now - timeWindowMs

        // Store state for mouse handling
        chartStateRef.current = { minTime, timeWindowMs, minFreq, freqRange, dims }

        // Draw axes
        drawAxes(ctx, dims)

        // Draw Y-axis labels
        ctx.font = '10px system-ui, -apple-system, sans-serif'
        ctx.fillStyle = COLORS.canvas.label
        ctx.textAlign = 'right'
        ctx.textBaseline = 'middle'

        const ySteps = 4
        for (let i = 0; i <= ySteps; i++) {
            const freq = minFreq + (freqRange * i) / ySteps
            const y = dims.padding.top + dims.chartHeight - (dims.chartHeight * i) / ySteps
            ctx.fillText(freq.toFixed(1), dims.padding.left - 6, y)

            // Draw grid line
            ctx.strokeStyle = COLORS.canvas.grid
            ctx.lineWidth = 1
            ctx.beginPath()
            ctx.moveTo(dims.padding.left, y)
            ctx.lineTo(dims.padding.left + dims.chartWidth, y)
            ctx.stroke()
        }

        // Draw X-axis labels (time)
        ctx.textAlign = 'center'
        ctx.textBaseline = 'top'
        const xSteps = 4
        for (let i = 0; i <= xSteps; i++) {
            const t = minTime + (timeWindowMs * i) / xSteps
            const x = dims.padding.left + (dims.chartWidth * i) / xSteps
            const date = new Date(t)

            // Format based on time range
            let label: string
            if (timeWindowMs <= 3600000) {
                // Hour or less: show mm:ss
                label = `${date.getMinutes().toString().padStart(2, '0')}:${date.getSeconds().toString().padStart(2, '0')}`
            } else if (timeWindowMs <= 86400000) {
                // Day or less: show HH:mm
                label = `${date.getHours().toString().padStart(2, '0')}:${date.getMinutes().toString().padStart(2, '0')}`
            } else {
                // Week: show day/month HH:mm
                label = `${date.getDate()}/${date.getMonth() + 1}`
            }
            ctx.fillText(label, x, dims.padding.top + dims.chartHeight + 6)
        }

        // Helper functions
        const timeToX = (timestamp: number) => {
            const t = (timestamp - minTime) / timeWindowMs
            return dims.padding.left + t * dims.chartWidth
        }

        const freqToY = (freq: number) => {
            const t = (freq - minFreq) / freqRange
            return dims.padding.top + dims.chartHeight - t * dims.chartHeight
        }

        // Clip to chart area
        ctx.save()
        ctx.beginPath()
        ctx.rect(dims.padding.left, dims.padding.top, dims.chartWidth, dims.chartHeight)
        ctx.clip()

        // Draw comparison data first (behind main data)
        if (showComparison && comparisonData.length > 0) {
            // Filled area
            ctx.beginPath()
            ctx.moveTo(timeToX(comparisonData[0].timestamp), dims.padding.top + dims.chartHeight)
            for (const point of comparisonData) {
                ctx.lineTo(timeToX(point.timestamp), freqToY(point.frequency))
            }
            ctx.lineTo(timeToX(comparisonData[comparisonData.length - 1].timestamp), dims.padding.top + dims.chartHeight)
            ctx.closePath()
            ctx.fillStyle = 'rgba(148, 163, 184, 0.1)'
            ctx.fill()

            // Line
            ctx.beginPath()
            ctx.moveTo(timeToX(comparisonData[0].timestamp), freqToY(comparisonData[0].frequency))
            for (let i = 1; i < comparisonData.length; i++) {
                ctx.lineTo(timeToX(comparisonData[i].timestamp), freqToY(comparisonData[i].frequency))
            }
            ctx.strokeStyle = COLORS.canvas.label
            ctx.lineWidth = 1.5
            ctx.setLineDash([4, 4])
            ctx.stroke()
            ctx.setLineDash([])

            // Dots
            for (const point of comparisonData) {
                ctx.beginPath()
                ctx.arc(timeToX(point.timestamp), freqToY(point.frequency), 3, 0, Math.PI * 2)
                ctx.fillStyle = COLORS.canvas.label
                ctx.fill()
            }
        }

        // Draw main data
        if (historyData.length > 0) {
            // Filled area
            ctx.beginPath()
            ctx.moveTo(timeToX(historyData[0].timestamp), dims.padding.top + dims.chartHeight)
            for (const point of historyData) {
                ctx.lineTo(timeToX(point.timestamp), freqToY(point.frequency))
            }
            ctx.lineTo(timeToX(historyData[historyData.length - 1].timestamp), dims.padding.top + dims.chartHeight)
            ctx.closePath()
            ctx.fillStyle = 'rgba(245, 158, 11, 0.15)'
            ctx.fill()

            // Line
            ctx.beginPath()
            ctx.moveTo(timeToX(historyData[0].timestamp), freqToY(historyData[0].frequency))
            for (let i = 1; i < historyData.length; i++) {
                ctx.lineTo(timeToX(historyData[i].timestamp), freqToY(historyData[i].frequency))
            }
            ctx.strokeStyle = '#f59e0b'
            ctx.lineWidth = 2
            ctx.stroke()

            // Dots
            for (const point of historyData) {
                ctx.beginPath()
                ctx.arc(timeToX(point.timestamp), freqToY(point.frequency), 3, 0, Math.PI * 2)
                ctx.fillStyle = '#f59e0b'
                ctx.fill()
            }
        }

        // Draw hovered point highlight
        if (hoveredPoint) {
            ctx.beginPath()
            ctx.arc(
                timeToX(hoveredPoint.point.timestamp),
                freqToY(hoveredPoint.point.frequency),
                6, 0, Math.PI * 2
            )
            ctx.strokeStyle = hoveredPoint.isComparison ? '#64748b' : '#d97706'
            ctx.lineWidth = 2
            ctx.stroke()
            ctx.fillStyle = '#fff'
            ctx.fill()
            ctx.beginPath()
            ctx.arc(
                timeToX(hoveredPoint.point.timestamp),
                freqToY(hoveredPoint.point.frequency),
                3, 0, Math.PI * 2
            )
            ctx.fillStyle = hoveredPoint.isComparison ? '#94a3b8' : '#f59e0b'
            ctx.fill()
        }

        ctx.restore()
    }, [historyData, comparisonData, showComparison, timeWindowMs, now, hoveredPoint, t])

    // Format timestamp for tooltip
    const formatTime = (timestamp: number) => {
        const date = new Date(timestamp)
        return `${date.getHours().toString().padStart(2, '0')}:${date.getMinutes().toString().padStart(2, '0')}:${date.getSeconds().toString().padStart(2, '0')}`
    }

    return (
        <div className="flex-1 flex flex-col overflow-hidden">
            {/* Stats bar */}
            <div className="flex-shrink-0 px-4 py-2 bg-slate-50 border-b border-slate-100">
                <div className="flex items-center justify-between">
                    <div className="text-sm font-medium text-slate-700">{infrastructure.name}</div>
                    {latestReading && (
                        <div className="flex items-center gap-4">
                            <div className="text-right">
                                <div className="text-xs text-slate-400">{t('shm.detail.currentFreq')}</div>
                                <div className="text-lg font-mono font-semibold text-amber-600">
                                    {latestReading.frequency.toFixed(2)} Hz
                                </div>
                            </div>
                            <div className="text-right">
                                <div className="text-xs text-slate-400">{t('shm.detail.amplitude')}</div>
                                <div className="text-lg font-mono font-semibold text-slate-700">
                                    {(latestReading.amplitude * 100).toFixed(0)}%
                                </div>
                            </div>
                        </div>
                    )}
                </div>
            </div>

            {/* Chart */}
            <div ref={containerRef} className="flex-1 relative min-h-0 p-2">
                <canvas
                    ref={canvasRef}
                    className="absolute inset-2 w-[calc(100%-16px)] h-[calc(100%-16px)] cursor-crosshair"
                    onMouseMove={handleMouseMove}
                    onMouseLeave={handleMouseLeave}
                />

                {/* Tooltip */}
                {hoveredPoint && (
                    <div
                        className="absolute pointer-events-none z-10 bg-white border border-slate-200 rounded-lg shadow-lg px-3 py-2 text-xs"
                        style={{
                            left: Math.min(hoveredPoint.x + 12, (containerRef.current?.clientWidth ?? 200) - 120),
                            top: Math.max(hoveredPoint.y - 60, 8)
                        }}
                    >
                        <div className="font-medium text-slate-700 mb-1">
                            {hoveredPoint.isComparison ? t('shm.detail.yesterday') : t('shm.detail.today')}
                        </div>
                        <div className="flex items-center gap-2 text-slate-600">
                            <span className="text-slate-400">{t('shm.detail.time')}:</span>
                            <span className="font-mono">{formatTime(hoveredPoint.point.timestamp)}</span>
                        </div>
                        <div className="flex items-center gap-2 text-slate-600">
                            <span className="text-slate-400">{t('shm.detail.freq')}:</span>
                            <span className={`font-mono font-semibold ${hoveredPoint.isComparison ? 'text-slate-600' : 'text-amber-600'}`}>
                                {hoveredPoint.point.frequency.toFixed(2)} Hz
                            </span>
                        </div>
                        <div className="flex items-center gap-2 text-slate-600">
                            <span className="text-slate-400">{t('shm.detail.amp')}:</span>
                            <span className="font-mono">{(hoveredPoint.point.amplitude * 100).toFixed(0)}%</span>
                        </div>
                    </div>
                )}

                {/* Legend */}
                {showComparison && comparisonData.length > 0 && (
                    <div className="absolute top-4 right-4 flex flex-col gap-1 text-xs">
                        <div className="flex items-center gap-2">
                            <div className="w-3 h-0.5 bg-amber-500" />
                            <span className="text-slate-600">{t('shm.detail.today')}</span>
                        </div>
                        <div className="flex items-center gap-2">
                            <div className="w-3 h-0.5 bg-slate-400 border-dashed border-t border-slate-400" style={{ borderStyle: 'dashed' }} />
                            <span className="text-slate-500">{t('shm.detail.yesterday')}</span>
                        </div>
                    </div>
                )}
            </div>

            {/* Summary stats */}
            {historyData.length > 0 && (
                <div className="flex-shrink-0 px-4 py-2 bg-slate-50 border-t border-slate-100">
                    <div className="grid grid-cols-3 gap-4 text-center">
                        <div>
                            <div className="text-[10px] text-slate-400 uppercase tracking-wide">{t('common.min')}</div>
                            <div className="text-sm font-mono font-medium text-slate-600">
                                {Math.min(...historyData.map(p => p.frequency)).toFixed(2)} Hz
                            </div>
                        </div>
                        <div>
                            <div className="text-[10px] text-slate-400 uppercase tracking-wide">{t('common.avg')}</div>
                            <div className="text-sm font-mono font-medium text-slate-600">
                                {(historyData.reduce((sum, p) => sum + p.frequency, 0) / historyData.length).toFixed(2)} Hz
                            </div>
                        </div>
                        <div>
                            <div className="text-[10px] text-slate-400 uppercase tracking-wide">{t('common.max')}</div>
                            <div className="text-sm font-mono font-medium text-slate-600">
                                {Math.max(...historyData.map(p => p.frequency)).toFixed(2)} Hz
                            </div>
                        </div>
                    </div>
                </div>
            )}
        </div>
    )
}
