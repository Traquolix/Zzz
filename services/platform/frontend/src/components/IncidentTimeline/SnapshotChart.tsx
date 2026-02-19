import { useMemo, useRef, useEffect } from 'react'
import type { IncidentSnapshot } from '@/types/incident'
import { getSpeedHexColor } from '@/lib/speedColors'

type ChannelSpeedData = {
    channel: number
    avgSpeed: number
    detectionCount: number
}

type Props = {
    snapshot: IncidentSnapshot
    height?: number
}

export function SnapshotChart({ snapshot, height = 128 }: Props) {
    const canvasRef = useRef<HTMLCanvasElement>(null)

    const channelData = useMemo((): ChannelSpeedData[] => {
        const byChannel = new Map<number, { speeds: number[]; count: number }>()

        snapshot.detections.forEach(d => {
            const existing = byChannel.get(d.channel)
            if (existing) {
                existing.speeds.push(d.speed)
                existing.count += d.count
            } else {
                byChannel.set(d.channel, { speeds: [d.speed], count: d.count })
            }
        })

        const result: ChannelSpeedData[] = []
        byChannel.forEach((data, channel) => {
            const avgSpeed = data.speeds.reduce((a, b) => a + b, 0) / data.speeds.length
            result.push({
                channel,
                avgSpeed,
                detectionCount: data.count
            })
        })

        return result.sort((a, b) => a.channel - b.channel)
    }, [snapshot])

    const stats = useMemo(() => {
        if (channelData.length === 0) return { avgSpeed: 0, minSpeed: 0, normalSpeed: 80 }

        const speeds = channelData.map(d => d.avgSpeed)
        const minSpeed = Math.min(...speeds)
        const sortedSpeeds = [...speeds].sort((a, b) => b - a)
        const topCount = Math.max(3, Math.floor(speeds.length * 0.3))
        const normalSpeed = sortedSpeeds.slice(0, topCount)
            .reduce((a, b) => a + b, 0) / topCount

        return {
            avgSpeed: speeds.reduce((a, b) => a + b, 0) / speeds.length,
            minSpeed,
            normalSpeed: Math.max(normalSpeed, 60)
        }
    }, [channelData])

    useEffect(() => {
        const canvas = canvasRef.current
        if (!canvas || channelData.length === 0) return

        const ctx = canvas.getContext('2d')
        if (!ctx) return

        const rect = canvas.getBoundingClientRect()
        const dpr = window.devicePixelRatio || 1
        canvas.width = rect.width * dpr
        canvas.height = rect.height * dpr
        ctx.scale(dpr, dpr)

        const width = rect.width
        const canvasHeight = rect.height
        const padding = { top: 8, right: 12, bottom: 24, left: 32 }
        const chartWidth = width - padding.left - padding.right
        const chartHeight = canvasHeight - padding.top - padding.bottom

        ctx.clearRect(0, 0, width, canvasHeight)

        const channels = channelData.map(d => d.channel)
        const minChannel = Math.min(...channels)
        const maxChannel = Math.max(...channels)
        const channelRange = maxChannel - minChannel || 1

        const maxSpeed = stats.normalSpeed * 1.15

        // Grid lines
        ctx.strokeStyle = '#e2e8f0'
        ctx.lineWidth = 1
        ctx.font = '10px system-ui, sans-serif'
        ctx.fillStyle = '#94a3b8'
        ctx.textAlign = 'right'

        const gridSpeeds = [0, Math.round(maxSpeed / 2), Math.round(maxSpeed)]
        gridSpeeds.forEach(speed => {
            const y = padding.top + chartHeight - (speed / maxSpeed) * chartHeight
            ctx.beginPath()
            ctx.moveTo(padding.left, y)
            ctx.lineTo(width - padding.right, y)
            ctx.stroke()
            if (speed > 0) {
                ctx.fillText(`${speed}`, padding.left - 6, y + 4)
            }
        })

        // Incident highlight band
        const incidentX = padding.left + ((snapshot.centerChannel - minChannel) / channelRange) * chartWidth
        const bandWidth = Math.max(20, chartWidth * 0.08)
        ctx.fillStyle = 'rgba(239, 68, 68, 0.08)'
        ctx.fillRect(incidentX - bandWidth / 2, padding.top, bandWidth, chartHeight)

        // Filled area chart
        if (channelData.length > 1) {
            const gradient = ctx.createLinearGradient(0, padding.top, 0, padding.top + chartHeight)
            gradient.addColorStop(0, 'rgba(34, 197, 94, 0.4)')
            gradient.addColorStop(0.5, 'rgba(234, 179, 8, 0.4)')
            gradient.addColorStop(1, 'rgba(239, 68, 68, 0.3)')

            ctx.beginPath()
            ctx.moveTo(padding.left, padding.top + chartHeight)

            channelData.forEach((d) => {
                const x = padding.left + ((d.channel - minChannel) / channelRange) * chartWidth
                const y = padding.top + chartHeight - (d.avgSpeed / maxSpeed) * chartHeight
                ctx.lineTo(x, y)
            })

            ctx.lineTo(padding.left + chartWidth, padding.top + chartHeight)
            ctx.closePath()
            ctx.fillStyle = gradient
            ctx.fill()

            // Line segments
            ctx.lineWidth = 2.5
            ctx.lineCap = 'round'
            ctx.lineJoin = 'round'

            for (let i = 0; i < channelData.length - 1; i++) {
                const d1 = channelData[i]
                const d2 = channelData[i + 1]
                const x1 = padding.left + ((d1.channel - minChannel) / channelRange) * chartWidth
                const y1 = padding.top + chartHeight - (d1.avgSpeed / maxSpeed) * chartHeight
                const x2 = padding.left + ((d2.channel - minChannel) / channelRange) * chartWidth
                const y2 = padding.top + chartHeight - (d2.avgSpeed / maxSpeed) * chartHeight

                const avgSpeed = (d1.avgSpeed + d2.avgSpeed) / 2
                ctx.strokeStyle = getSpeedHexColor(avgSpeed, stats.normalSpeed)
                ctx.beginPath()
                ctx.moveTo(x1, y1)
                ctx.lineTo(x2, y2)
                ctx.stroke()
            }
        }

        // Incident marker line
        ctx.strokeStyle = '#dc2626'
        ctx.lineWidth = 2
        ctx.setLineDash([])
        ctx.beginPath()
        ctx.moveTo(incidentX, padding.top)
        ctx.lineTo(incidentX, padding.top + chartHeight)
        ctx.stroke()

        // Incident marker triangle
        ctx.fillStyle = '#dc2626'
        ctx.beginPath()
        ctx.moveTo(incidentX, padding.top)
        ctx.lineTo(incidentX - 6, padding.top - 8)
        ctx.lineTo(incidentX + 6, padding.top - 8)
        ctx.closePath()
        ctx.fill()

        // X-axis labels
        ctx.textAlign = 'center'
        ctx.font = '10px system-ui, sans-serif'
        ctx.fillStyle = '#64748b'

        const distances = [-200, 0, 200]
        distances.forEach(dist => {
            const channel = snapshot.centerChannel + dist / 10
            if (channel >= minChannel - 5 && channel <= maxChannel + 5) {
                const x = padding.left + ((channel - minChannel) / channelRange) * chartWidth
                const label = dist === 0 ? 'Incident' : `${dist > 0 ? '+' : ''}${dist}m`
                ctx.fillText(label, x, canvasHeight - 6)
            }
        })

    }, [channelData, stats, snapshot.centerChannel])

    if (snapshot.detections.length === 0) {
        return (
            <div className="h-32 flex items-center justify-center text-slate-400 text-sm">
                No detection data captured
            </div>
        )
    }

    const slowdownPct = stats.normalSpeed > 0
        ? Math.round((1 - stats.minSpeed / stats.normalSpeed) * 100)
        : 0

    return (
        <div>
            {/* Header with key metrics */}
            <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-4">
                    <div>
                        <div className="text-[10px] uppercase tracking-wide text-slate-400 mb-0.5">Avg Speed</div>
                        <div className="text-lg font-semibold text-slate-700">{Math.round(stats.avgSpeed)} <span className="text-xs font-normal text-slate-400">km/h</span></div>
                    </div>
                    <div className="w-px h-8 bg-slate-200" />
                    <div>
                        <div className="text-[10px] uppercase tracking-wide text-slate-400 mb-0.5">Min Speed</div>
                        <div className={`text-lg font-semibold ${slowdownPct > 50 ? 'text-red-600' : slowdownPct > 20 ? 'text-orange-500' : 'text-slate-700'}`}>
                            {Math.round(stats.minSpeed)} <span className="text-xs font-normal text-slate-400">km/h</span>
                        </div>
                    </div>
                    {slowdownPct > 10 && (
                        <>
                            <div className="w-px h-8 bg-slate-200" />
                            <div>
                                <div className="text-[10px] uppercase tracking-wide text-slate-400 mb-0.5">Slowdown</div>
                                <div className={`text-lg font-semibold ${slowdownPct > 50 ? 'text-red-600' : 'text-orange-500'}`}>
                                    {slowdownPct}<span className="text-xs font-normal">%</span>
                                </div>
                            </div>
                        </>
                    )}
                </div>
                <div className="text-[10px] text-slate-400">
                    30s window · {channelData.length} positions
                </div>
            </div>

            {/* Chart */}
            <canvas ref={canvasRef} className="w-full rounded" style={{ height }} />

            {/* Legend */}
            <div className="flex items-center justify-center gap-6 mt-2 text-[10px] text-slate-400">
                <span className="flex items-center gap-1.5">
                    <span className="w-3 h-0.5 bg-green-500 rounded" /> Normal
                </span>
                <span className="flex items-center gap-1.5">
                    <span className="w-3 h-0.5 bg-yellow-500 rounded" /> Slowing
                </span>
                <span className="flex items-center gap-1.5">
                    <span className="w-3 h-0.5 bg-red-500 rounded" /> Slow
                </span>
            </div>
        </div>
    )
}
