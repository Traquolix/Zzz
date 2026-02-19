import { useEffect, useRef, useState, useCallback } from 'react'
import type { SectionDataPoint, HoveredSectionPoint } from './types'
import { TIME_WINDOW_MS } from './types'
import type { SectionStats } from '@/hooks/useSectionStats'
import {
    setupCanvas,
    getChartDimensions,
    drawBackground,
    drawAxes,
    drawSpeedGrid,
    drawYAxisLabel,
    drawTimeXAxis,
    drawLineWithDots,
    clipToChartArea,
    timeToX,
    speedToY,
    computeYAxisRange,
    type ChartPadding,
} from '@/lib/chartUtils'

function formatTravelTime(seconds: number | null): string {
    if (seconds === null || seconds <= 0) return '—'
    if (seconds < 60) return `${Math.round(seconds)}s`
    const minutes = Math.floor(seconds / 60)
    const secs = Math.round(seconds % 60)
    return secs > 0 ? `${minutes}m ${secs}s` : `${minutes}m`
}

type SectionDetailProps = {
    stats: SectionStats
    historyData: SectionDataPoint[]
    now: number
}

export function SectionDetail({
    stats,
    historyData,
    now,
}: SectionDetailProps) {
    const canvasRef = useRef<HTMLCanvasElement>(null)
    const containerRef = useRef<HTMLDivElement>(null)
    const [hoveredPoint, setHoveredPoint] = useState<HoveredSectionPoint>(null)

    const chartConfig = { padding: { top: 28, right: 20, bottom: 28, left: 52 } }

    // With directional fibers, only one direction has data
    const dir0 = stats.direction0
    const dir1 = stats.direction1
    const hasDir0Data = dir0 && dir0.vehicleCount > 0
    const hasDir1Data = dir1 && dir1.vehicleCount > 0

    // Determine which direction this fiber represents
    const activeDir = hasDir0Data ? dir0 : (hasDir1Data ? dir1 : null)
    const activeVehicleCount = activeDir?.vehicleCount ?? 0

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

        // Get all speeds to determine Y scale (use whichever direction has data)
        const allSpeeds: number[] = []
        historyData.forEach(p => {
            if (p.speed0 !== null) allSpeeds.push(p.speed0)
            if (p.speed1 !== null) allSpeeds.push(p.speed1)
        })
        const yRange = computeYAxisRange(allSpeeds)

        drawAxes(ctx, dimensions)
        drawSpeedGrid(ctx, dimensions, yRange)
        drawYAxisLabel(ctx, dimensions)
        drawTimeXAxis(ctx, dimensions, minTime, TIME_WINDOW_MS)

        if (historyData.length === 0) return

        const visibleData = historyData.filter(p => p.timestamp > minTime)
        if (visibleData.length === 0) return

        clipToChartArea(ctx, dimensions)

        // Draw direction 0 data if available
        const points0 = visibleData
            .filter(p => p.speed0 !== null)
            .map(p => ({
                x: timeToX(p.timestamp, minTime, TIME_WINDOW_MS, dimensions),
                y: speedToY(p.speed0!, yRange, dimensions)
            }))
        if (points0.length > 0) {
            drawLineWithDots(ctx, points0, '#3b82f6', 2.5, 4)
        }

        // Draw direction 1 data if available
        const points1 = visibleData
            .filter(p => p.speed1 !== null)
            .map(p => ({
                x: timeToX(p.timestamp, minTime, TIME_WINDOW_MS, dimensions),
                y: speedToY(p.speed1!, yRange, dimensions)
            }))
        if (points1.length > 0) {
            drawLineWithDots(ctx, points1, '#3b82f6', 2.5, 4)
        }

        ctx.restore()
    }, [historyData, now])

    const handleMouseMove = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
        const canvas = canvasRef.current
        if (!canvas || historyData.length === 0) {
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

        const allSpeeds: number[] = []
        historyData.forEach(p => {
            if (p.speed0 !== null) allSpeeds.push(p.speed0)
            if (p.speed1 !== null) allSpeeds.push(p.speed1)
        })
        const yRange = computeYAxisRange(allSpeeds)

        const visibleData = historyData.filter(p => p.timestamp > minTime)

        let closestPoint: HoveredSectionPoint = null
        let closestDist = Infinity

        // Check direction 0 points
        visibleData.forEach(p => {
            if (p.speed0 === null) return
            const x = padding.left + ((p.timestamp - minTime) / TIME_WINDOW_MS) * chartWidth
            const normalizedY = (p.speed0 - yRange.min) / (yRange.max - yRange.min)
            const y = padding.top + (1 - normalizedY) * chartHeight
            const dist = Math.sqrt((mouseX - x) ** 2 + (mouseY - y) ** 2)
            if (dist < 20 && dist < closestDist) {
                closestPoint = {
                    speed: p.speed0,
                    timestamp: p.timestamp,
                    direction: 0,
                    count: p.count0,
                    x,
                    y
                }
                closestDist = dist
            }
        })

        // Check direction 1 points
        visibleData.forEach(p => {
            if (p.speed1 === null) return
            const x = padding.left + ((p.timestamp - minTime) / TIME_WINDOW_MS) * chartWidth
            const normalizedY = (p.speed1 - yRange.min) / (yRange.max - yRange.min)
            const y = padding.top + (1 - normalizedY) * chartHeight
            const dist = Math.sqrt((mouseX - x) ** 2 + (mouseY - y) ** 2)
            if (dist < 20 && dist < closestDist) {
                closestPoint = {
                    speed: p.speed1,
                    timestamp: p.timestamp,
                    direction: 1,
                    count: p.count1,
                    x,
                    y
                }
                closestDist = dist
            }
        })

        setHoveredPoint(closestPoint)
    }, [historyData, now])

    const handleMouseLeave = useCallback(() => {
        setHoveredPoint(null)
    }, [])

    return (
        <>
            {/* Stats - single card for the active direction */}
            <div className="px-4 py-3 border-b border-slate-100 bg-gradient-to-b from-slate-50 to-white flex-shrink-0">
                <div className="bg-blue-50/60 rounded-lg px-3 py-2.5 border border-blue-100/50">
                    <div className="flex items-center gap-2 mb-1.5">
                        <span className="w-3 h-3 rounded-full bg-blue-500" />
                        <span className="text-xs font-medium text-blue-600">Traffic Statistics</span>
                    </div>
                    <div className={`text-xl font-bold ${activeVehicleCount > 0 ? 'text-slate-800' : 'text-slate-300'}`}>
                        {activeDir?.avgSpeed != null ? `${Math.round(activeDir.avgSpeed)}` : '—'}
                        <span className="text-sm font-medium text-slate-400 ml-1">km/h</span>
                    </div>
                    <div className="flex items-center gap-3 mt-1 text-xs text-slate-500">
                        <span>{formatTravelTime(activeDir?.travelTime ?? null)}</span>
                        <span className={activeVehicleCount > 0 ? 'text-blue-600 font-medium' : ''}>
                            {activeVehicleCount} vehicles
                        </span>
                    </div>
                </div>
            </div>

            {/* Graph */}
            <div ref={containerRef} className="flex-1 relative min-h-0">
                <canvas
                    ref={canvasRef}
                    className="absolute inset-0 w-full h-full"
                    onMouseMove={handleMouseMove}
                    onMouseLeave={handleMouseLeave}
                />
                {historyData.length === 0 && (
                    <div className="absolute inset-0 flex items-center justify-center">
                        <span className="text-sm text-slate-400">Waiting for data...</span>
                    </div>
                )}

                {hoveredPoint && (
                    <div
                        className="absolute pointer-events-none bg-slate-800 text-white text-xs px-2.5 py-1.5 rounded shadow-lg z-10"
                        style={{
                            left: Math.min(hoveredPoint.x + 10, (containerRef.current?.clientWidth || 200) - 120),
                            top: Math.max(hoveredPoint.y - 40, 5)
                        }}
                    >
                        <div className="font-medium">{hoveredPoint.speed.toFixed(1)} km/h</div>
                        <div className="text-slate-300 text-[10px]">
                            {new Date(hoveredPoint.timestamp).toLocaleTimeString()}
                        </div>
                        <div className="text-slate-300 text-[10px]">
                            {hoveredPoint.count} vehicle{hoveredPoint.count !== 1 ? 's' : ''}
                        </div>
                    </div>
                )}
            </div>
        </>
    )
}
