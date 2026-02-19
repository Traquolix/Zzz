import { useEffect, useRef, useState, useMemo, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { OccupancyChart } from './OccupancyChart'
import type { DataPoint, HoveredPoint } from './types'
import { TIME_WINDOW_MS } from './types'
import {
    setupCanvas,
    getChartDimensions,
    drawBackground,
    drawAxes,
    drawSpeedGrid,
    drawYAxisLabel,
    drawTimeXAxis,
    drawNoDataMessage,
    drawDataPoint,
    clipToChartArea,
    timeToX,
    speedToY,
    computeYAxisRange,
    type ChartPadding,
} from '@/lib/chartUtils'

type ViewMode = 'scatter' | 'occupancy'

type SelectedLandmark = {
    fiberId: string
    channel: number
    lng: number
    lat: number
}

type LandmarkDetailProps = {
    selectedLandmark: SelectedLandmark
    selectedName: string | null
    visiblePoints: DataPoint[]
    onFlyTo: (lng: number, lat: number) => void
    onRename: (name: string) => void
    now: number
}

export function LandmarkDetail({
    selectedLandmark,
    selectedName,
    visiblePoints,
    onFlyTo,
    onRename,
    now,
}: LandmarkDetailProps) {
    const { t } = useTranslation()
    const canvasRef = useRef<HTMLCanvasElement>(null)
    const containerRef = useRef<HTMLDivElement>(null)
    const [hoveredPoint, setHoveredPoint] = useState<HoveredPoint>(null)
    const [isEditingName, setIsEditingName] = useState(false)
    const [nameInput, setNameInput] = useState('')
    const [viewMode, setViewMode] = useState<ViewMode>('scatter')

    const chartConfig = useMemo(() => {
        const padding = { top: 28, right: 20, bottom: 28, left: 52 }
        return { padding }
    }, [])

    const selectedStats = useMemo(() => {
        if (visiblePoints.length === 0) {
            return { avg: 0, min: 0, max: 0, count: 0 }
        }
        const speeds = visiblePoints.map(p => p.speed)
        return {
            avg: (speeds.reduce((a, b) => a + b, 0) / speeds.length).toFixed(1),
            min: Math.min(...speeds).toFixed(1),
            max: Math.max(...speeds).toFixed(1),
            count: visiblePoints.reduce((sum, p) => sum + p.count, 0)
        }
    }, [visiblePoints])

    const getPointColor = useCallback((_direction: 0 | 1) => {
        // Single direction per fiber now, use consistent blue color
        return '#3b82f6'
    }, [])

    const startEditing = useCallback(() => {
        setNameInput(selectedName || '')
        setIsEditingName(true)
    }, [selectedName])

    const saveName = useCallback(() => {
        if (nameInput.trim()) {
            onRename(nameInput.trim())
        }
        setIsEditingName(false)
    }, [nameInput, onRename])

    // Draw canvas
    useEffect(() => {
        const canvas = canvasRef.current
        if (!canvas) return

        const setup = setupCanvas(canvas)
        if (!setup) return
        const { ctx, width, height } = setup

        const { padding } = chartConfig
        const dimensions = getChartDimensions(width, height, padding as ChartPadding)

        ctx.clearRect(0, 0, width, height)
        drawBackground(ctx, width, height)

        const minTime = now - TIME_WINDOW_MS
        const speeds = visiblePoints.map(p => p.speed)
        const yRange = computeYAxisRange(speeds)

        drawAxes(ctx, dimensions)
        drawSpeedGrid(ctx, dimensions, yRange)
        drawYAxisLabel(ctx, dimensions)
        drawTimeXAxis(ctx, dimensions, minTime, TIME_WINDOW_MS)

        if (visiblePoints.length > 0) {
            clipToChartArea(ctx, dimensions)
            visiblePoints.forEach(point => {
                const x = timeToX(point.timestamp, minTime, TIME_WINDOW_MS, dimensions)
                const y = speedToY(point.speed, yRange, dimensions)
                const radius = 3 + Math.min(point.count, 4)
                const isHovered = hoveredPoint?.point === point
                const color = getPointColor(point.direction)

                drawDataPoint(ctx, x, y, radius, color, isHovered)
            })
            ctx.restore()
        } else {
            drawNoDataMessage(ctx, width, height, t('map.landmark.waitingForDetections'))
        }
    }, [visiblePoints, now, chartConfig, hoveredPoint, getPointColor])

    const handleMouseMove = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
        const canvas = canvasRef.current
        if (!canvas || visiblePoints.length === 0) {
            setHoveredPoint(null)
            return
        }

        const rect = canvas.getBoundingClientRect()
        const mouseX = e.clientX - rect.left
        const mouseY = e.clientY - rect.top

        const { padding } = chartConfig
        const chartWidth = rect.width - padding.left - padding.right
        const chartHeight = rect.height - padding.top - padding.bottom
        const minTime = now - TIME_WINDOW_MS
        const speeds = visiblePoints.map(p => p.speed)
        const yRange = computeYAxisRange(speeds)

        let closestPoint: DataPoint | null = null
        let closestDist = Infinity
        let closestX = 0
        let closestY = 0

        visiblePoints.forEach(point => {
            const x = padding.left + ((point.timestamp - minTime) / TIME_WINDOW_MS) * chartWidth
            const normalizedY = (point.speed - yRange.min) / (yRange.max - yRange.min)
            const y = padding.top + (1 - normalizedY) * chartHeight
            const dist = Math.sqrt((mouseX - x) ** 2 + (mouseY - y) ** 2)

            if (dist < 20 && dist < closestDist) {
                closestPoint = point
                closestDist = dist
                closestX = x
                closestY = y
            }
        })

        if (closestPoint) {
            setHoveredPoint({ point: closestPoint, x: closestX, y: closestY })
        } else {
            setHoveredPoint(null)
        }
    }, [visiblePoints, chartConfig, now])

    const handleMouseLeave = useCallback(() => {
        setHoveredPoint(null)
    }, [])

    return (
        <>
            {/* Header */}
            <div className="px-4 py-3 border-b border-slate-100 bg-gradient-to-b from-slate-50 to-white flex-shrink-0">
                <div className="flex items-center justify-between mb-2">
                    <div className="min-w-0 flex-1">
                        {isEditingName ? (
                            <input
                                type="text"
                                value={nameInput}
                                onChange={(e) => setNameInput(e.target.value)}
                                onKeyDown={(e) => {
                                    if (e.key === 'Enter') saveName()
                                    if (e.key === 'Escape') setIsEditingName(false)
                                }}
                                onBlur={saveName}
                                autoFocus
                                placeholder={t('map.landmark.namePlaceholder')}
                                className="w-full border border-slate-300 rounded px-2 py-1 text-sm font-semibold focus:outline-none focus:ring-1 focus:ring-blue-500"
                            />
                        ) : (
                            <div
                                className="font-semibold text-slate-800 text-sm truncate cursor-text hover:text-blue-600"
                                onClick={startEditing}
                                title={t('map.landmark.clickToRename')}
                            >
                                {selectedName || `Channel ${selectedLandmark.channel}`}
                            </div>
                        )}
                        <div className="text-[11px] text-slate-400">
                            {selectedLandmark.fiberId} · Ch. {selectedLandmark.channel}
                        </div>
                    </div>
                    <button
                        onClick={() => onFlyTo(selectedLandmark.lng, selectedLandmark.lat)}
                        className="p-1.5 text-slate-400 hover:text-blue-500 transition-colors ml-2"
                        title={t('map.landmark.goToLocation')}
                    >
                        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
                        </svg>
                    </button>
                </div>

                {/* Stats row */}
                <div className="flex items-center gap-4">
                    <div>
                        <div className="text-[10px] uppercase tracking-wide text-slate-400">{t('map.landmark.avgSpeed')}</div>
                        <div className="text-base font-semibold text-slate-700">
                            {selectedStats.avg} <span className="text-xs font-normal text-slate-400">km/h</span>
                        </div>
                    </div>
                    <div className="w-px h-7 bg-slate-200" />
                    <div>
                        <div className="text-[10px] uppercase tracking-wide text-slate-400">{t('map.landmark.range')}</div>
                        <div className="text-base font-semibold text-slate-600">
                            {selectedStats.min} – {selectedStats.max}
                        </div>
                    </div>
                    <div className="w-px h-7 bg-slate-200" />
                    <div>
                        <div className="text-[10px] uppercase tracking-wide text-slate-400">{t('map.landmark.vehicles')}</div>
                        <div className="text-base font-semibold text-blue-600">{selectedStats.count}</div>
                    </div>
                </div>
            </div>

            {/* Chart */}
            <div ref={containerRef} className="flex-1 relative min-h-0">
                {viewMode === 'scatter' ? (
                    <>
                        <canvas
                            ref={canvasRef}
                            className="absolute inset-0 w-full h-full"
                            onMouseMove={handleMouseMove}
                            onMouseLeave={handleMouseLeave}
                        />

                        {hoveredPoint && (
                            <div
                                className="absolute pointer-events-none bg-slate-800 text-white text-xs px-2.5 py-1.5 rounded shadow-lg z-10"
                                style={{
                                    left: Math.min(hoveredPoint.x + 10, (containerRef.current?.clientWidth || 200) - 120),
                                    top: Math.max(hoveredPoint.y - 40, 5)
                                }}
                            >
                                <div className="font-medium">{hoveredPoint.point.speed.toFixed(1)} km/h</div>
                                <div className="text-slate-300 text-[10px]">
                                    {new Date(hoveredPoint.point.timestamp).toLocaleTimeString()}
                                </div>
                                <div className="text-slate-300 text-[10px]">
                                    {hoveredPoint.point.count} vehicle{hoveredPoint.point.count !== 1 ? 's' : ''}
                                </div>
                            </div>
                        )}
                    </>
                ) : (
                    <OccupancyChart
                        visiblePoints={visiblePoints}
                        now={now}
                    />
                )}
            </div>

            {/* Footer with view mode toggle */}
            <div className="px-4 py-2 border-t border-slate-100 flex items-center justify-end gap-2 flex-shrink-0 bg-gradient-to-b from-white to-slate-50">
                <div className="flex items-center gap-1 text-xs">
                    <button
                        onClick={() => setViewMode('scatter')}
                        className={`px-2 py-1 rounded transition-colors ${
                            viewMode === 'scatter'
                                ? 'bg-slate-200 text-slate-700 font-medium'
                                : 'text-slate-400 hover:bg-slate-100'
                        }`}
                    >
                        {t('chart.scatter')}
                    </button>
                    <button
                        onClick={() => setViewMode('occupancy')}
                        className={`px-2 py-1 rounded transition-colors ${
                            viewMode === 'occupancy'
                                ? 'bg-slate-200 text-slate-700 font-medium'
                                : 'text-slate-400 hover:bg-slate-100'
                        }`}
                    >
                        {t('chart.occupancy')}
                    </button>
                </div>
            </div>
        </>
    )
}
