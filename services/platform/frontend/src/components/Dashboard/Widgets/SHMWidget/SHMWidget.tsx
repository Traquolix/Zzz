import { useEffect, useState, useMemo, useCallback } from 'react'
import { useRealtime } from '@/hooks/useRealtime'
import { useInfrastructure } from '@/hooks/useInfrastructure'
import { useFibers } from '@/hooks/useFibers'
import { useMapInstance } from '@/hooks/useMapInstance'
import type { Infrastructure } from '@/types/infrastructure'
import { parseFrequencyReadings } from '@/lib/parseMessage'
import { InfrastructureList } from './InfrastructureList'
import { InfrastructureDetail } from './InfrastructureDetail'

// Time range options - peaks are estimated every few minutes, so longer ranges make sense
export type TimeRange = {
    label: string
    ms: number
}

const TIME_RANGES: TimeRange[] = [
    { label: '1 Hour', ms: 60 * 60 * 1000 },
    { label: '6 Hours', ms: 6 * 60 * 60 * 1000 },
    { label: '24 Hours', ms: 24 * 60 * 60 * 1000 },
    { label: '7 Days', ms: 7 * 24 * 60 * 60 * 1000 },
]

export type FrequencyDataPoint = {
    timestamp: number
    frequency: number
    amplitude: number
}

export function SHMWidget() {
    const { infrastructures, selectedInfrastructure, selectInfrastructure, latestReadings } = useInfrastructure()
    const { fibers } = useFibers()
    const { subscribe } = useRealtime()
    const { fitBoundsWithLayer, ensureLayerVisible } = useMapInstance()

    const [frequencyHistory, setFrequencyHistory] = useState<Map<string, FrequencyDataPoint[]>>(new Map())
    const [now, setNow] = useState(() => Date.now())
    const [timeRange, setTimeRange] = useState<TimeRange>(TIME_RANGES[0])
    const [showComparison, setShowComparison] = useState(false)

    // Update time every second
    useEffect(() => {
        const interval = setInterval(() => setNow(Date.now()), 1000)
        return () => clearInterval(interval)
    }, [])

    // Subscribe to SHM readings
    useEffect(() => {
        return subscribe('shm_readings', (data: unknown) => {
            const readings = parseFrequencyReadings(data)
            if (readings.length === 0) return

            // Keep data for the longest time range (7 days)
            const maxTimeWindow = 7 * 24 * 60 * 60 * 1000
            const cutoffTime = Date.now() - maxTimeWindow

            setFrequencyHistory(prev => {
                const next = new Map(prev)

                for (const reading of readings) {
                    const existing = next.get(reading.infrastructureId) || []
                    const filtered = existing.filter(p => p.timestamp > cutoffTime)
                    next.set(reading.infrastructureId, [
                        ...filtered,
                        {
                            timestamp: reading.timestamp,
                            frequency: reading.frequency,
                            amplitude: reading.amplitude
                        }
                    ])
                }

                return next
            })
        })
    }, [subscribe])

    // Handle infrastructure selection
    const handleSelect = useCallback((infra: Infrastructure) => {
        ensureLayerVisible('infrastructure')
        selectInfrastructure({
            id: infra.id,
            name: infra.name,
            type: infra.type,
            fiberId: infra.fiberId,
            startChannel: infra.startChannel,
            endChannel: infra.endChannel
        })
    }, [ensureLayerVisible, selectInfrastructure])

    // Handle fly to infrastructure
    const handleFlyTo = useCallback((infra: Infrastructure, e: React.MouseEvent) => {
        e.stopPropagation()
        const fiber = fibers.find(f => f.parentFiberId === infra.fiberId)
        if (fiber) {
            const startCoord = fiber.coordinates[infra.startChannel]
            const endCoord = fiber.coordinates[infra.endChannel]
            if (startCoord && endCoord) {
                fitBoundsWithLayer([startCoord, endCoord], 'infrastructure', 80, 3000)
            }
        }
    }, [fibers, fitBoundsWithLayer])

    // Get history for selected infrastructure within current time range
    const selectedHistory = useMemo(() => {
        if (!selectedInfrastructure) return []
        const history = frequencyHistory.get(selectedInfrastructure.id) || []
        const minTime = now - timeRange.ms
        return history.filter(p => p.timestamp > minTime)
    }, [selectedInfrastructure, frequencyHistory, now, timeRange])

    // Get comparison data (yesterday's data shifted to align with today)
    const comparisonData = useMemo(() => {
        if (!showComparison || !selectedInfrastructure) return []
        const history = frequencyHistory.get(selectedInfrastructure.id) || []

        // Get data from yesterday (shifted by 24 hours)
        const oneDayMs = 24 * 60 * 60 * 1000
        const minTime = now - timeRange.ms - oneDayMs
        const maxTime = now - oneDayMs

        return history
            .filter(p => p.timestamp > minTime && p.timestamp <= maxTime)
            .map(p => ({
                ...p,
                // Shift timestamp forward by 24 hours to align with today
                timestamp: p.timestamp + oneDayMs
            }))
    }, [showComparison, selectedInfrastructure, frequencyHistory, now, timeRange])

    const hasInfrastructures = infrastructures.length > 0

    return (
        <div className="h-full flex flex-col bg-white overflow-hidden">
            {/* Header */}
            <div className="flex-shrink-0 px-4 py-3 border-b border-slate-200 bg-gradient-to-b from-slate-50 to-white">
                <div className="flex items-center gap-2">
                    <svg className="w-4 h-4 text-amber-500" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 21h19.5m-18-18v18m10.5-18v18m6-13.5V21M6.75 6.75h.75m-.75 3h.75m-.75 3h.75m3-6h.75m-.75 3h.75m-.75 3h.75M6.75 21v-3.375c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125V21M3 3h12m-.75 4.5H21m-3.75 3H21m-3.75 3H21" />
                    </svg>
                    <h2 className="text-sm font-semibold text-slate-700">Structural Health</h2>
                    {hasInfrastructures && (
                        <span className="ml-auto px-1.5 py-0.5 rounded-full text-[10px] bg-amber-100 text-amber-600">
                            {infrastructures.length}
                        </span>
                    )}
                </div>
            </div>

            {/* Empty state */}
            {!hasInfrastructures && (
                <div className="flex-1 flex items-center justify-center text-slate-400 text-sm bg-gradient-to-b from-slate-50 to-white">
                    <div className="text-center px-4">
                        <svg className="w-10 h-10 mx-auto mb-2 text-slate-200" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 21h19.5m-18-18v18m10.5-18v18m6-13.5V21M6.75 6.75h.75m-.75 3h.75m-.75 3h.75m3-6h.75m-.75 3h.75m-.75 3h.75M6.75 21v-3.375c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125V21M3 3h12m-.75 4.5H21m-3.75 3H21m-3.75 3H21" />
                        </svg>
                        <div className="font-medium text-slate-500 mb-1">No infrastructure</div>
                        <div className="text-xs text-slate-400">No bridges or tunnels are configured</div>
                    </div>
                </div>
            )}

            {/* Content */}
            {hasInfrastructures && (
                <>
                    <InfrastructureList
                        infrastructures={infrastructures}
                        latestReadings={latestReadings}
                        selectedId={selectedInfrastructure?.id ?? null}
                        onSelect={handleSelect}
                        onFlyTo={handleFlyTo}
                    />

                    {selectedInfrastructure ? (
                        <>
                            {/* Controls bar */}
                            <div className="flex-shrink-0 px-4 py-2 border-b border-slate-100 bg-white">
                                <div className="flex items-center justify-between gap-4">
                                    {/* Time range selector */}
                                    <div className="flex items-center gap-2">
                                        <span className="text-xs text-slate-400">Range:</span>
                                        <select
                                            value={timeRange.ms}
                                            onChange={(e) => {
                                                const range = TIME_RANGES.find(r => r.ms === Number(e.target.value))
                                                if (range) setTimeRange(range)
                                            }}
                                            className="text-xs px-2 py-1 border border-slate-200 rounded bg-white text-slate-600 focus:outline-none focus:ring-1 focus:ring-amber-500"
                                        >
                                            {TIME_RANGES.map(range => (
                                                <option key={range.ms} value={range.ms}>
                                                    {range.label}
                                                </option>
                                            ))}
                                        </select>
                                    </div>

                                    {/* Comparison toggle */}
                                    <label className="flex items-center gap-2 cursor-pointer">
                                        <input
                                            type="checkbox"
                                            checked={showComparison}
                                            onChange={(e) => setShowComparison(e.target.checked)}
                                            className="w-3.5 h-3.5 rounded border-slate-300 text-amber-500 focus:ring-amber-500"
                                        />
                                        <span className="text-xs text-slate-600">Compare yesterday</span>
                                    </label>
                                </div>
                            </div>

                            <InfrastructureDetail
                                infrastructure={selectedInfrastructure}
                                latestReading={latestReadings.get(selectedInfrastructure.id) ?? null}
                                historyData={selectedHistory}
                                comparisonData={comparisonData}
                                timeRange={timeRange}
                                showComparison={showComparison}
                                now={now}
                            />
                        </>
                    ) : (
                        <div className="flex-1 flex items-center justify-center text-slate-400 text-sm">
                            <div className="text-center px-4">
                                <svg className="w-8 h-8 mx-auto mb-2 text-slate-200" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                                    <path strokeLinecap="round" strokeLinejoin="round" d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 013 19.875v-6.75zM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V8.625zM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V4.125z" />
                                </svg>
                                <div className="text-xs leading-relaxed">
                                    Select infrastructure above to view<br />
                                    frequency monitoring data
                                </div>
                            </div>
                        </div>
                    )}
                </>
            )}
        </div>
    )
}
