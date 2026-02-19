import { useMemo, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import type { Incident } from '@/types/incident'
import { AlertTriangle, TrendingDown, TrafficCone, HelpCircle, CheckCircle } from 'lucide-react'
import { SEVERITY_DOT, SEVERITY_TEXT } from '@/constants/incidents'

type Props = {
    incidents: Incident[]
    selectedIncidentId?: string | null
    onSelectIncident?: (incident: Incident) => void
    isNewIncident?: (id: string) => boolean
}

type MiniNavProps = {
    incidents: Incident[]
    onScrollTo: (id: string) => void
}

const SEVERITY_COLORS = SEVERITY_DOT
const SEVERITY_TEXT_COLORS = SEVERITY_TEXT

const TYPE_ICONS = {
    slowdown: TrendingDown,
    congestion: TrafficCone,
    accident: AlertTriangle,
    anomaly: HelpCircle,
}

function formatTime(dateStr: string): string {
    const date = new Date(dateStr)
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

function formatDate(dateStr: string): string {
    const date = new Date(dateStr)
    return date.toLocaleDateString([], { month: 'short', day: 'numeric' })
}

function formatDuration(ms: number): string {
    const minutes = Math.floor(ms / 60000)
    const hours = Math.floor(minutes / 60)
    if (hours > 0) {
        return `${hours}h ${minutes % 60}m`
    }
    return `${minutes}m`
}

function getTimeBetween(date1: string, date2: string): number {
    return Math.abs(new Date(date1).getTime() - new Date(date2).getTime())
}

// Threshold for showing ellipsis (30 minutes)
const GAP_THRESHOLD = 30 * 60 * 1000

type TimelineItem =
    | { type: 'incident'; incident: Incident }
    | { type: 'gap'; duration: number }
    | { type: 'date'; date: string }

function MiniNav({ incidents, onScrollTo }: MiniNavProps) {
    const { t } = useTranslation()
    // Group by date for mini navigation
    const dateGroups = useMemo(() => {
        const groups: { date: string; incidents: Incident[] }[] = []
        let currentDate: string | null = null

        const sorted = [...incidents].sort((a, b) =>
            new Date(b.detectedAt).getTime() - new Date(a.detectedAt).getTime()
        )

        for (const incident of sorted) {
            const date = formatDate(incident.detectedAt)
            if (date !== currentDate) {
                groups.push({ date, incidents: [] })
                currentDate = date
            }
            groups[groups.length - 1].incidents.push(incident)
        }

        return groups
    }, [incidents])

    if (dateGroups.length <= 1) return null

    return (
        <div className="fixed top-20 right-6 bg-white rounded-lg shadow-md border p-3 z-10 max-w-[140px]">
            <div className="text-[10px] text-slate-400 uppercase tracking-wide mb-2">
                {t('incidents.quickNav')}
            </div>
            <div className="space-y-1">
                {dateGroups.map(({ date, incidents: groupIncidents }) => (
                    <button
                        key={date}
                        onClick={() => onScrollTo(groupIncidents[0].id)}
                        className="w-full flex items-center justify-between gap-2 px-2 py-1 rounded hover:bg-slate-50 transition-colors text-left"
                    >
                        <span className="text-xs font-medium text-slate-700">{date}</span>
                        <span className="text-[10px] text-slate-400">{groupIncidents.length}</span>
                    </button>
                ))}
            </div>
        </div>
    )
}

export function IncidentTimeline({ incidents, selectedIncidentId, onSelectIncident, isNewIncident }: Props) {
    const { t } = useTranslation()
    const itemRefs = useRef<Map<string, HTMLDivElement>>(new Map())

    const scrollToIncident = (id: string) => {
        const element = itemRefs.current.get(id)
        if (element) {
            element.scrollIntoView({ behavior: 'smooth', block: 'start' })
        }
    }

    // Sort by date, newest first
    const sortedIncidents = useMemo(() => {
        return [...incidents].sort((a, b) =>
            new Date(b.detectedAt).getTime() - new Date(a.detectedAt).getTime()
        )
    }, [incidents])

    // Build timeline items with gaps and date separators
    const timelineItems = useMemo(() => {
        const items: TimelineItem[] = []
        let lastDate: string | null = null

        for (let i = 0; i < sortedIncidents.length; i++) {
            const incident = sortedIncidents[i]
            const incidentDate = formatDate(incident.detectedAt)

            // Add date separator if new day
            if (incidentDate !== lastDate) {
                items.push({ type: 'date', date: incidentDate })
                lastDate = incidentDate
            }

            // Check for gap with previous incident
            if (i > 0) {
                const gap = getTimeBetween(sortedIncidents[i - 1].detectedAt, incident.detectedAt)
                if (gap > GAP_THRESHOLD) {
                    items.push({ type: 'gap', duration: gap })
                }
            }

            items.push({ type: 'incident', incident })
        }

        return items
    }, [sortedIncidents])

    if (incidents.length === 0) {
        return (
            <div className="flex items-center justify-center h-64 text-slate-400">
                {t('incidents.noIncidents')}
            </div>
        )
    }

    return (
        <div className="relative">
            {/* Hide MiniNav when detail panel is open */}
            {!selectedIncidentId && (
                <MiniNav incidents={incidents} onScrollTo={scrollToIncident} />
            )}

            {/* Timeline line - centered at 24px */}
            <div className="absolute left-6 top-0 bottom-0 w-px bg-slate-200" />

            <div className="space-y-0">
                {timelineItems.map((item, index) => {
                    if (item.type === 'date') {
                        return (
                            <div key={`date-${index}`} className="relative pl-14 py-3">
                                <div className="absolute left-4 w-4 h-4 rounded-full bg-slate-300 border-2 border-white" />
                                <span className="text-xs font-medium text-slate-500 uppercase tracking-wide">
                                    {item.date}
                                </span>
                            </div>
                        )
                    }

                    if (item.type === 'gap') {
                        return (
                            <div key={`gap-${index}`} className="relative pl-14 py-4">
                                <div className="flex items-center justify-center gap-1.5">
                                    <div className="w-1 h-1 rounded-full bg-slate-300" />
                                    <div className="w-1 h-1 rounded-full bg-slate-300" />
                                    <div className="w-1 h-1 rounded-full bg-slate-300" />
                                    <span className="text-xs text-slate-400 italic ml-2">
                                        {formatDuration(item.duration)}
                                    </span>
                                </div>
                            </div>
                        )
                    }

                    const { incident } = item
                    const Icon = TYPE_ICONS[incident.type]
                    const isResolved = incident.status === 'resolved'
                    const isSelected = selectedIncidentId === incident.id
                    const isNew = isNewIncident?.(incident.id) ?? false

                    return (
                        <div
                            key={incident.id}
                            ref={(el) => {
                                if (el) itemRefs.current.set(incident.id, el)
                            }}
                            className="relative pl-14 py-2 group flex items-center"
                        >
                            {/* Timeline dot - vertically centered with card */}
                            <div
                                className={`absolute left-4 w-4 h-4 rounded-full border-2 shadow-sm transition-all ${
                                    isSelected
                                        ? 'border-blue-500 ring-2 ring-blue-200'
                                        : 'border-white'
                                } ${
                                    isResolved ? 'bg-slate-400' : SEVERITY_COLORS[incident.severity]
                                }`}
                                style={{ top: '50%', transform: 'translateY(-50%)' }}
                            />

                            {/* Incident card */}
                            <div
                                onClick={() => onSelectIncident?.(incident)}
                                className={`flex-1 bg-white rounded-lg border p-3 shadow-sm transition-all cursor-pointer ${
                                    isSelected
                                        ? 'ring-2 ring-blue-500 border-blue-500 shadow-md'
                                        : isNew
                                        ? 'ring-2 ring-blue-300 border-blue-300 shadow-md animate-pulse'
                                        : 'hover:shadow-md hover:border-slate-300'
                                } ${
                                    isResolved && !isSelected ? 'opacity-60' : ''
                                }`}
                            >
                                <div className="flex items-start justify-between gap-3">
                                    <div className="flex items-center gap-2">
                                        <Icon className={`h-4 w-4 ${isResolved ? 'text-slate-400' : SEVERITY_TEXT_COLORS[incident.severity]}`} />
                                        <span className="font-medium text-sm text-slate-900">
                                            {t(`incidents.types.${incident.type}`)}
                                        </span>
                                        {isResolved && (
                                            <CheckCircle className="h-3.5 w-3.5 text-green-500" />
                                        )}
                                        {isNew && (
                                            <span className="text-[9px] font-bold uppercase tracking-wider text-blue-600 bg-blue-50 px-1.5 py-0.5 rounded animate-pulse">
                                                {t('incidents.new')}
                                            </span>
                                        )}
                                    </div>
                                    <span className="text-xs text-slate-500">
                                        {formatTime(incident.detectedAt)}
                                    </span>
                                </div>

                                <div className="mt-1.5 flex items-center gap-3 text-xs text-slate-500">
                                    <span className="capitalize">{t(`incidents.severity.${incident.severity}`)}</span>
                                    <span className="text-slate-300">|</span>
                                    <span>{incident.fiberLine}</span>
                                    <span className="text-slate-300">|</span>
                                    <span>Ch. {incident.channel}</span>
                                    {incident.duration && (
                                        <>
                                            <span className="text-slate-300">|</span>
                                            <span>{formatDuration(incident.duration)}</span>
                                        </>
                                    )}
                                </div>
                            </div>
                        </div>
                    )
                })}
            </div>
        </div>
    )
}
