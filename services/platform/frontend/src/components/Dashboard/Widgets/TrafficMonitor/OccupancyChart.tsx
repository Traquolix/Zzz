import { useEffect, useRef, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import type { DataPoint } from './types'
import { TIME_WINDOW_MS } from './types'
import { getSpeedHexColor } from '@/lib/speedColors'
import { COLORS } from '@/lib/theme'
import {
    setupCanvas,
    getChartDimensions,
    drawBackground,
    drawAxes,
    drawTimeXAxis,
    drawNoDataMessage,
    clipToChartArea,
    type ChartPadding,
} from '@/lib/chartUtils'

const MAX_SLOTS = 3
const BUCKET_MS = 1000

type OccupancyBucket = {
    count: number
    speedSum: number
    weightSum: number
}

type OccupancyChartProps = {
    visiblePoints: DataPoint[]
    now: number
}

export function OccupancyChart({ visiblePoints, now }: OccupancyChartProps) {
    const { t } = useTranslation()
    const canvasRef = useRef<HTMLCanvasElement>(null)

    const buckets = useMemo(() => {
        const minTime = now - TIME_WINDOW_MS
        const numBuckets = Math.ceil(TIME_WINDOW_MS / BUCKET_MS)
        const result: OccupancyBucket[] = Array.from({ length: numBuckets }, () => ({
            count: 0,
            speedSum: 0,
            weightSum: 0,
        }))

        for (const point of visiblePoints) {
            const bucketIdx = Math.floor((point.timestamp - minTime) / BUCKET_MS)
            if (bucketIdx >= 0 && bucketIdx < numBuckets) {
                const bucket = result[bucketIdx]
                bucket.count = Math.min(bucket.count + point.count, MAX_SLOTS)
                bucket.speedSum += point.speed * point.count
                bucket.weightSum += point.count
            }
        }

        return result
    }, [visiblePoints, now])

    useEffect(() => {
        const canvas = canvasRef.current
        if (!canvas) return

        const setup = setupCanvas(canvas)
        if (!setup) return
        const { ctx, width, height } = setup

        const padding: ChartPadding = { top: 28, right: 20, bottom: 28, left: 52 }
        const dimensions = getChartDimensions(width, height, padding)
        const { chartWidth, chartHeight } = dimensions
        const minTime = now - TIME_WINDOW_MS

        ctx.clearRect(0, 0, width, height)
        drawBackground(ctx, width, height)
        drawAxes(ctx, dimensions)
        drawTimeXAxis(ctx, dimensions, minTime, TIME_WINDOW_MS)

        // Draw Y-axis labels for slots
        ctx.font = '12px system-ui, -apple-system, sans-serif'
        ctx.fillStyle = COLORS.canvas.axis
        ctx.textAlign = 'right'
        ctx.textBaseline = 'middle'
        for (let slot = 1; slot <= MAX_SLOTS; slot++) {
            const y = padding.top + chartHeight - (slot / MAX_SLOTS) * chartHeight + (chartHeight / MAX_SLOTS) / 2
            ctx.fillText(`${slot}`, padding.left - 10, y)
        }

        // Draw Y-axis unit label
        ctx.font = '11px system-ui, -apple-system, sans-serif'
        ctx.fillStyle = COLORS.canvas.label
        ctx.textAlign = 'left'
        ctx.textBaseline = 'bottom'
        ctx.fillText(t('traffic.occupancy.slots'), padding.left, padding.top - 6)

        // Draw horizontal slot dividers
        ctx.strokeStyle = COLORS.canvas.grid
        ctx.lineWidth = 1
        for (let slot = 1; slot < MAX_SLOTS; slot++) {
            const y = padding.top + chartHeight - (slot / MAX_SLOTS) * chartHeight
            ctx.beginPath()
            ctx.moveTo(padding.left + 1, y)
            ctx.lineTo(padding.left + chartWidth, y)
            ctx.stroke()
        }

        if (visiblePoints.length === 0) {
            drawNoDataMessage(ctx, width, height, t('traffic.occupancy.waitingForDetections'))
            return
        }

        // Draw occupancy cells
        clipToChartArea(ctx, dimensions)

        const numBuckets = buckets.length
        const cellWidth = chartWidth / numBuckets
        const slotHeight = chartHeight / MAX_SLOTS

        for (let i = 0; i < numBuckets; i++) {
            const bucket = buckets[i]
            const x = padding.left + i * cellWidth

            // Draw empty cell background for all slots
            for (let slot = 0; slot < MAX_SLOTS; slot++) {
                const y = padding.top + chartHeight - (slot + 1) * slotHeight
                ctx.fillStyle = COLORS.canvas.grid
                ctx.fillRect(x + 0.5, y + 0.5, cellWidth - 1, slotHeight - 1)
            }

            // Fill occupied slots from bottom up, colored by speed
            if (bucket.count > 0) {
                const avgSpeed = bucket.weightSum > 0 ? bucket.speedSum / bucket.weightSum : 0
                const color = getSpeedHexColor(avgSpeed)

                for (let slot = 0; slot < bucket.count; slot++) {
                    const y = padding.top + chartHeight - (slot + 1) * slotHeight
                    ctx.fillStyle = color
                    ctx.fillRect(x + 0.5, y + 0.5, cellWidth - 1, slotHeight - 1)
                }
            }
        }

        ctx.restore()
    }, [buckets, visiblePoints, now, t])

    return (
        <canvas
            ref={canvasRef}
            className="absolute inset-0 w-full h-full"
        />
    )
}
