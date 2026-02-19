import { useState, useEffect, useMemo } from 'react'
import { Loader2 } from 'lucide-react'
import { fetchPeakFrequencies } from '@/api/infrastructure'
import type { PeakFrequencyData } from '@/types/infrastructure'

type Props = {
    infrastructureId: string
    width?: number
    height?: number
}

/**
 * Mini peak frequency scatter chart for list view.
 * Shows last day's data in a compact format without axes labels.
 */
export function MiniPeakChart({ infrastructureId, width = 200, height = 60 }: Props) {
    const [data, setData] = useState<PeakFrequencyData | null>(null)
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState(false)

    const padding = { top: 4, right: 4, bottom: 4, left: 4 }
    const plotWidth = width - padding.left - padding.right
    const plotHeight = height - padding.top - padding.bottom

    // Fetch last day's peak data
    useEffect(() => {
        async function load() {
            setLoading(true)
            setError(false)
            try {
                // Get last 24 hours of data
                const now = new Date()
                const oneDayAgo = new Date(now.getTime() - 24 * 60 * 60 * 1000)

                const peaks = await fetchPeakFrequencies({
                    maxSamples: 500,
                    startTime: oneDayAgo,
                    endTime: now,
                })
                setData(peaks)
            } catch (err) {
                console.error('Failed to load mini peak data:', err)
                setError(true)
            } finally {
                setLoading(false)
            }
        }
        load()
    }, [infrastructureId])

    // Process points
    const points = useMemo(() => {
        if (!data || data.dt.length === 0) return []

        const freqMin = 1.05
        const freqMax = 1.20
        const duration = (data.dt[data.dt.length - 1] || 1) * 1000

        const xScale = (offsetSec: number) => padding.left + ((offsetSec * 1000) / duration) * plotWidth
        const yScale = (f: number) => padding.top + ((freqMax - f) / (freqMax - freqMin)) * plotHeight

        return data.dt.map((offsetSec, i) => {
            const freq = data.peakFrequencies[i]
            const inRange = freq >= freqMin && freq <= freqMax
            return {
                x: xScale(offsetSec),
                y: yScale(freq),
                inRange,
            }
        }).filter(pt => pt.inRange)
    }, [data, plotWidth, plotHeight, padding.left, padding.top])

    if (loading) {
        return (
            <div
                className="flex items-center justify-center bg-slate-50 rounded"
                style={{ width, height }}
            >
                <Loader2 className="w-4 h-4 animate-spin text-slate-300" />
            </div>
        )
    }

    if (error || !data || points.length === 0) {
        return (
            <div
                className="flex items-center justify-center bg-slate-50 rounded text-xs text-slate-400"
                style={{ width, height }}
            >
                No data
            </div>
        )
    }

    return (
        <svg width={width} height={height} className="bg-slate-50 rounded">
            {/* Background grid lines */}
            <line
                x1={padding.left}
                y1={height / 2}
                x2={width - padding.right}
                y2={height / 2}
                stroke="#e2e8f0"
                strokeWidth={1}
                strokeDasharray="2,2"
            />

            {/* Data points */}
            {points.map((pt, i) => (
                <circle
                    key={i}
                    cx={pt.x}
                    cy={pt.y}
                    r={1.5}
                    fill="#f59e0b"
                    fillOpacity={0.4}
                />
            ))}
        </svg>
    )
}
