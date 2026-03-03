import { useMemo, useState, useRef, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { useIncidents } from '@/hooks/useIncidents'
import { useFibers } from '@/hooks/useFibers'
import { useMapInstance } from '@/hooks/useMapInstance'
import { useMapSelection } from '@/hooks/useMapSelection'
import { useIncidentSnapshot } from '@/hooks/useIncidentSnapshot'
import { IncidentActionBar } from '@/components/IncidentTimeline/IncidentActionBar'
import { getSpeedHexColor } from '@/lib/speedColors'
import { COLORS } from '@/lib/theme'
import type { Incident, IncidentSnapshot } from '@/types/incident'
import { SEVERITY_BADGE, SEVERITY_INDICATOR as SEVERITY_INDICATOR_SHARED } from '@/constants/incidents'

const SEVERITY_COLORS = SEVERITY_BADGE

type SnapshotChartProps = {
    snapshot: IncidentSnapshot
}

type ChannelSpeedData = {
    channel: number
    avgSpeed: number
    detectionCount: number
}

function SnapshotChart({ snapshot }: SnapshotChartProps) {
    const canvasRef = useRef<HTMLCanvasElement>(null)
    const { t } = useTranslation()

    // Aggregate detections by channel to get average speed at each position
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
        const height = rect.height
        const padding = { top: 8, right: 12, bottom: 24, left: 32 }
        const chartWidth = width - padding.left - padding.right
        const chartHeight = height - padding.top - padding.bottom

        ctx.clearRect(0, 0, width, height)

        // Find channel range
        const channels = channelData.map(d => d.channel)
        const minChannel = Math.min(...channels)
        const maxChannel = Math.max(...channels)
        const channelRange = maxChannel - minChannel || 1

        const maxSpeed = stats.normalSpeed * 1.15

        // Draw subtle horizontal grid lines (just 2)
        ctx.strokeStyle = COLORS.canvas.grid
        ctx.lineWidth = 1
        ctx.font = '10px system-ui, sans-serif'
        ctx.fillStyle = COLORS.canvas.label
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

        // Draw incident highlight band (subtle red vertical band)
        const incidentX = padding.left + ((snapshot.centerChannel - minChannel) / channelRange) * chartWidth
        const bandWidth = Math.max(20, chartWidth * 0.08)
        ctx.fillStyle = 'rgba(239, 68, 68, 0.08)'
        ctx.fillRect(incidentX - bandWidth / 2, padding.top, bandWidth, chartHeight)

        // Draw filled area chart with gradient
        if (channelData.length > 1) {
            // Create gradient based on position
            const gradient = ctx.createLinearGradient(0, padding.top, 0, padding.top + chartHeight)
            gradient.addColorStop(0, 'rgba(34, 197, 94, 0.4)')
            gradient.addColorStop(0.5, 'rgba(234, 179, 8, 0.4)')
            gradient.addColorStop(1, 'rgba(239, 68, 68, 0.3)')

            // Draw filled area
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

            // Draw the line on top with color based on speed
            ctx.lineWidth = 2.5
            ctx.lineCap = 'round'
            ctx.lineJoin = 'round'

            // Draw line segments with color based on speed
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

        // Draw incident marker line
        ctx.strokeStyle = COLORS.severity.critical
        ctx.lineWidth = 2
        ctx.setLineDash([])
        ctx.beginPath()
        ctx.moveTo(incidentX, padding.top)
        ctx.lineTo(incidentX, padding.top + chartHeight)
        ctx.stroke()

        // Draw incident marker triangle at top
        ctx.fillStyle = COLORS.severity.critical
        ctx.beginPath()
        ctx.moveTo(incidentX, padding.top)
        ctx.lineTo(incidentX - 6, padding.top - 8)
        ctx.lineTo(incidentX + 6, padding.top - 8)
        ctx.closePath()
        ctx.fill()

        // X-axis labels
        ctx.textAlign = 'center'
        ctx.font = '10px system-ui, sans-serif'
        ctx.fillStyle = COLORS.canvas.axis

        const incidentLabel = t('incidents.snapshot.incident')
        const distances = [-200, 0, 200]
        distances.forEach(dist => {
            const channel = snapshot.centerChannel + dist / 10
            if (channel >= minChannel - 5 && channel <= maxChannel + 5) {
                const x = padding.left + ((channel - minChannel) / channelRange) * chartWidth
                const label = dist === 0 ? incidentLabel : `${dist > 0 ? '+' : ''}${dist}m`
                ctx.fillText(label, x, height - 6)
            }
        })

    }, [channelData, stats, snapshot.centerChannel, t])

    if (snapshot.detections.length === 0) {
        return (
            <div className="h-48 flex items-center justify-center text-slate-400 text-sm">
                {t('incidents.noDetectionData')}
            </div>
        )
    }

    const slowdownPct = stats.normalSpeed > 0
        ? Math.round((1 - stats.minSpeed / stats.normalSpeed) * 100)
        : 0

    return (
        <div className="px-4 py-3 bg-gradient-to-b from-slate-50 to-white border-t border-slate-200">
            {/* Header with key metrics */}
            <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-4">
                    <div>
                        <div className="text-[10px] uppercase tracking-wide text-slate-400 mb-0.5">{t('incidents.snapshot.avgSpeed')}</div>
                        <div className="text-lg font-semibold text-slate-700">{Math.round(stats.avgSpeed)} <span className="text-xs font-normal text-slate-400">km/h</span></div>
                    </div>
                    <div className="w-px h-8 bg-slate-200" />
                    <div>
                        <div className="text-[10px] uppercase tracking-wide text-slate-400 mb-0.5">{t('incidents.snapshot.minSpeed')}</div>
                        <div className={`text-lg font-semibold ${slowdownPct > 50 ? 'text-red-600' : slowdownPct > 20 ? 'text-orange-500' : 'text-slate-700'}`}>
                            {Math.round(stats.minSpeed)} <span className="text-xs font-normal text-slate-400">km/h</span>
                        </div>
                    </div>
                    {slowdownPct > 10 && (
                        <>
                            <div className="w-px h-8 bg-slate-200" />
                            <div>
                                <div className="text-[10px] uppercase tracking-wide text-slate-400 mb-0.5">{t('incidents.snapshot.slowdown')}</div>
                                <div className={`text-lg font-semibold ${slowdownPct > 50 ? 'text-red-600' : 'text-orange-500'}`}>
                                    {slowdownPct}<span className="text-xs font-normal">%</span>
                                </div>
                            </div>
                        </>
                    )}
                </div>
                <div className="text-[10px] text-slate-400">
                    {t('incidents.snapshot.window')} · {t('incidents.snapshot.positions', { count: channelData.length })}
                </div>
            </div>

            {/* Chart */}
            <canvas ref={canvasRef} className="w-full h-32 rounded" />

            {/* Minimal legend */}
            <div className="flex items-center justify-center gap-6 mt-2 text-[10px] text-slate-400">
                <span className="flex items-center gap-1.5">
                    <span className="w-3 h-0.5 bg-green-500 rounded" /> {t('incidents.snapshot.legendNormal')}
                </span>
                <span className="flex items-center gap-1.5">
                    <span className="w-3 h-0.5 bg-yellow-500 rounded" /> {t('incidents.snapshot.legendSlowing')}
                </span>
                <span className="flex items-center gap-1.5">
                    <span className="w-3 h-0.5 bg-red-500 rounded" /> {t('incidents.snapshot.legendSlow')}
                </span>
            </div>
        </div>
    )
}

type IncidentRowProps = {
    incident: Incident
    isSelected: boolean
    isExpanded: boolean
    isNew: boolean
    onToggleExpand: () => void
    onClick: () => void
    updateIncidentStatus?: (incidentId: string, newStatus: any) => void
}

const SEVERITY_INDICATOR = SEVERITY_INDICATOR_SHARED

function computeTimeAgo(detectedAt: string, t: (key: string, opts?: Record<string, unknown>) => string): string {
    const diff = Date.now() - new Date(detectedAt).getTime()
    const minutes = Math.floor(diff / 60000)
    if (minutes < 1) return t('incidents.time.justNow')
    if (minutes < 60) return t('incidents.time.minutesAgo', { count: minutes })
    const hours = Math.floor(minutes / 60)
    return t('incidents.time.hoursAgo', { count: hours })
}

type FilterType = 'all' | Incident['type']
type FilterSeverity = 'all' | Incident['severity']
type SortOption = 'severity' | 'recent' | 'oldest' | 'type'

const SEVERITY_ORDER = { critical: 0, high: 1, medium: 2, low: 3 }
const TYPE_ORDER = { accident: 0, slowdown: 1, congestion: 2, anomaly: 3 }

function IncidentRow({ incident, isSelected, isExpanded, isNew, onToggleExpand, onClick, updateIncidentStatus }: IncidentRowProps & { updateIncidentStatus: (incidentId: string, newStatus: any) => void }) {
    const { t } = useTranslation()
    const colors = SEVERITY_COLORS[incident.severity] || SEVERITY_COLORS.low
    const indicator = SEVERITY_INDICATOR[incident.severity] || SEVERITY_INDICATOR.low
    const { snapshot, loading, error, fetchSnapshot } = useIncidentSnapshot()
    const [timeAgo, setTimeAgo] = useState(() => computeTimeAgo(incident.detectedAt, t))

    useEffect(() => {
        setTimeAgo(computeTimeAgo(incident.detectedAt, t))
        const interval = setInterval(() => {
            setTimeAgo(computeTimeAgo(incident.detectedAt, t))
        }, 60000)
        return () => clearInterval(interval)
    }, [incident.detectedAt, t])

    const handleExpandClick = (e: React.MouseEvent) => {
        e.stopPropagation()
        if (!isExpanded) {
            fetchSnapshot(incident.id)
        }
        onToggleExpand()
    }

    return (
        <div
            className={`transition-all ${
                isSelected
                    ? 'bg-slate-50 ring-1 ring-inset ring-blue-200'
                    : 'bg-white hover:bg-slate-50/50'
            }`}
        >
            <div
                onClick={onClick}
                className="px-4 py-3 cursor-pointer"
            >
                <div className="flex items-start justify-between gap-3">
                    <div className="flex items-start gap-3 min-w-0">
                        {/* Severity indicator dot */}
                        <div className="pt-1.5 flex-shrink-0">
                            <div className={`w-2.5 h-2.5 rounded-full ${indicator.color} ${indicator.pulse ? 'animate-pulse' : ''}`} />
                        </div>
                        <div className="min-w-0">
                            <div className="flex items-center gap-2">
                                <span className="font-medium text-slate-800">
                                    {t(`incidents.types.${incident.type}`, { defaultValue: incident.type })}
                                </span>
                                <span className={`text-[10px] font-medium uppercase tracking-wide ${colors.text}`}>
                                    {t(`incidents.severity.${incident.severity}`, { defaultValue: incident.severity })}
                                </span>
                                {isNew && (
                                    <span className="text-[9px] font-bold uppercase tracking-wider text-blue-600 bg-blue-50 px-1.5 py-0.5 rounded animate-pulse">
                                        {t('incidents.new')}
                                    </span>
                                )}
                            </div>
                            <div className="text-xs text-slate-400 mt-0.5">
                                {incident.fiberLine} · Ch. {incident.channel}
                            </div>
                        </div>
                    </div>
                    <div className="flex items-center gap-2 flex-shrink-0">
                        <span className="text-xs text-slate-400">{timeAgo}</span>
                        <button
                            onClick={handleExpandClick}
                            className="p-1.5 text-slate-400 hover:text-slate-600 rounded-md hover:bg-slate-100 transition-colors"
                            title={isExpanded ? t('incidents.hideDetails') : t('incidents.showDetails')}
                        >
                            <svg
                                className={`w-4 h-4 transition-transform duration-200 ${isExpanded ? 'rotate-180' : ''}`}
                                fill="none"
                                stroke="currentColor"
                                viewBox="0 0 24 24"
                                aria-hidden="true"
                            >
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M19 9l-7 7-7-7" />
                            </svg>
                        </button>
                    </div>
                </div>
            </div>

            {isExpanded && (
                <>
                    {loading ? (
                        <div className="px-4 py-6 bg-gradient-to-b from-slate-50 to-white border-t border-slate-100">
                            <div className="flex items-center justify-center gap-2 text-sm text-slate-400">
                                <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24" aria-hidden="true">
                                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                                </svg>
                                {t('incidents.loadingSnapshot')}
                            </div>
                        </div>
                    ) : error ? (
                        <div className="px-4 py-6 bg-gradient-to-b from-slate-50 to-white border-t border-slate-100 text-sm text-slate-400 text-center">
                            {error}
                        </div>
                    ) : snapshot ? (
                        <SnapshotChart snapshot={snapshot} />
                    ) : null}

                    <div className="px-4 py-4 bg-gradient-to-b from-slate-50 to-white border-t border-slate-100">
                        <IncidentActionBar
                            incident={incident}
                            onStatusChange={updateIncidentStatus}
                        />
                    </div>
                </>
            )}
        </div>
    )
}

export function IncidentWidget() {
    const { t } = useTranslation()
    const { incidents, loading, isNewIncident, updateIncidentStatus } = useIncidents()
    const { getPosition } = useFibers()
    const { flyToWithLayer, ready: mapReady } = useMapInstance()
    const { selectedIncident, selectIncident } = useMapSelection()
    const [filterType, setFilterType] = useState<FilterType>('all')
    const [filterSeverity, setFilterSeverity] = useState<FilterSeverity>('all')
    const [sortBy, setSortBy] = useState<SortOption>('severity')
    const [expandedIncidentId, setExpandedIncidentId] = useState<string | null>(null)

    const activeIncidents = useMemo(() => {
        return incidents
            .filter(i => i.status === 'active')
            .filter(i => filterType === 'all' || i.type === filterType)
            .filter(i => filterSeverity === 'all' || i.severity === filterSeverity)
            .sort((a, b) => {
                switch (sortBy) {
                    case 'severity': {
                        const aSev = SEVERITY_ORDER[a.severity] ?? 4
                        const bSev = SEVERITY_ORDER[b.severity] ?? 4
                        if (aSev !== bSev) return aSev - bSev
                        return new Date(b.detectedAt).getTime() - new Date(a.detectedAt).getTime()
                    }
                    case 'recent':
                        return new Date(b.detectedAt).getTime() - new Date(a.detectedAt).getTime()
                    case 'oldest':
                        return new Date(a.detectedAt).getTime() - new Date(b.detectedAt).getTime()
                    case 'type': {
                        const aType = TYPE_ORDER[a.type] ?? 4
                        const bType = TYPE_ORDER[b.type] ?? 4
                        if (aType !== bType) return aType - bType
                        return new Date(b.detectedAt).getTime() - new Date(a.detectedAt).getTime()
                    }
                    default:
                        return 0
                }
            })
    }, [incidents, filterType, filterSeverity, sortBy])

    const totalActive = useMemo(() => incidents.filter(i => i.status === 'active').length, [incidents])

    const stats = useMemo(() => {
        const bySeverity = { critical: 0, high: 0, medium: 0, low: 0 }
        activeIncidents.forEach(i => {
            if (i.severity in bySeverity) {
                bySeverity[i.severity as keyof typeof bySeverity]++
            }
        })
        return bySeverity
    }, [activeIncidents])

    if (loading) {
        return (
            <div className="h-full flex items-center justify-center text-slate-400 text-sm">
                {t('incidents.loadingIncidents')}
            </div>
        )
    }

    const hasFilters = filterType !== 'all' || filterSeverity !== 'all'

    const handleIncidentClick = (incident: Incident) => {
        const pos = getPosition(incident.fiberLine, incident.channel, 0)
        if (!pos) return

        selectIncident({
            id: incident.id,
            type: incident.type,
            severity: incident.severity,
            fiberLine: incident.fiberLine,
            channel: incident.channel,
            lng: pos.lng,
            lat: pos.lat
        })

        if (mapReady) {
            flyToWithLayer(pos.lng, pos.lat, 'incidents', 17)
        }
    }

    return (
        <div className="h-full flex flex-col bg-white">
            {/* Header */}
            <div className="px-4 py-4 border-b border-slate-100">
                <div className="flex items-center justify-between mb-3">
                    <h2 className="text-base font-semibold text-slate-800">
                        {t('incidents.activeIncidents')}
                    </h2>
                    <div className="flex items-center gap-3">
                        {stats.critical > 0 && (
                            <div className="flex items-center gap-1.5">
                                <span className="w-2 h-2 rounded-full bg-red-500 animate-pulse" />
                                <span className="text-xs font-medium text-red-600">{t('incidents.critical', { count: stats.critical })}</span>
                            </div>
                        )}
                        <span className="text-sm text-slate-400">
                            {hasFilters
                                ? t('incidents.ofTotal', { count: activeIncidents.length, total: totalActive })
                                : t('incidents.total', { count: totalActive })
                            }
                        </span>
                    </div>
                </div>

                {/* Filters and Sort */}
                <div className="flex gap-2 flex-wrap">
                    <select
                        value={filterType}
                        onChange={(e) => setFilterType(e.target.value as FilterType)}
                        className="text-xs px-3 py-1.5 border border-slate-200 rounded-md bg-white text-slate-600 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-400 transition-colors"
                    >
                        <option value="all">{t('incidents.filters.allTypes')}</option>
                        <option value="slowdown">{t('incidents.types.slowdown')}</option>
                        <option value="congestion">{t('incidents.types.congestion')}</option>
                        <option value="accident">{t('incidents.types.accident')}</option>
                        <option value="anomaly">{t('incidents.types.anomaly')}</option>
                    </select>
                    <select
                        value={filterSeverity}
                        onChange={(e) => setFilterSeverity(e.target.value as FilterSeverity)}
                        className="text-xs px-3 py-1.5 border border-slate-200 rounded-md bg-white text-slate-600 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-400 transition-colors"
                    >
                        <option value="all">{t('incidents.filters.allSeverities')}</option>
                        <option value="critical">{t('incidents.severity.critical')}</option>
                        <option value="high">{t('incidents.severity.high')}</option>
                        <option value="medium">{t('incidents.severity.medium')}</option>
                        <option value="low">{t('incidents.severity.low')}</option>
                    </select>
                    <select
                        value={sortBy}
                        onChange={(e) => setSortBy(e.target.value as SortOption)}
                        className="text-xs px-3 py-1.5 border border-slate-200 rounded-md bg-white text-slate-600 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-400 transition-colors"
                    >
                        <option value="severity">{t('incidents.sort.severity')}</option>
                        <option value="recent">{t('incidents.sort.recent')}</option>
                        <option value="oldest">{t('incidents.sort.oldest')}</option>
                        <option value="type">{t('incidents.sort.type')}</option>
                    </select>
                </div>
            </div>

            {/* Incident list */}
            <div className="flex-1 overflow-y-auto">
                {activeIncidents.length === 0 ? (
                    <div className="h-full flex flex-col items-center justify-center text-slate-400 py-12">
                        <svg className="w-12 h-12 mb-3 text-slate-200" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                        </svg>
                        <span className="text-sm">{t('incidents.noActiveIncidents')}</span>
                    </div>
                ) : (
                    <div className="divide-y divide-slate-100">
                        {activeIncidents.map(incident => (
                            <IncidentRow
                                key={incident.id}
                                incident={incident}
                                isSelected={selectedIncident?.id === incident.id}
                                isExpanded={expandedIncidentId === incident.id}
                                isNew={isNewIncident(incident.id)}
                                onToggleExpand={() => setExpandedIncidentId(
                                    expandedIncidentId === incident.id ? null : incident.id
                                )}
                                onClick={() => handleIncidentClick(incident)}
                                updateIncidentStatus={updateIncidentStatus}
                            />
                        ))}
                    </div>
                )}
            </div>
        </div>
    )
}
