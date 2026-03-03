import { cn } from '@/lib/utils'
import { incidents, severityColor, timeSeries, fibers, getSpeedColor } from '../data'
import type { Section } from '../types'
import { TimeSeriesChart } from './TimeSeriesChart'
import { Sparkline } from './Sparkline'

interface AnalysisViewProps {
    sections: Section[]
    selectedIncidentId: string | null
    selectedSectionId: string | null
    onBack: () => void
}

export function AnalysisView({ sections, selectedIncidentId, selectedSectionId, onBack }: AnalysisViewProps) {
    const incident = selectedIncidentId ? incidents.find((i) => i.id === selectedIncidentId) : null
    const section = selectedSectionId ? sections.find((s) => s.id === selectedSectionId) : null

    if (!incident && !section) return null

    return (
        <div className="proto-analysis-enter h-full flex flex-col bg-[var(--proto-base)] overflow-y-auto">
            {/* Sticky header */}
            <div className="sticky top-0 z-10 bg-[var(--proto-base)] border-b border-[var(--proto-border)] px-5 py-3 flex items-center gap-3">
                <button
                    onClick={onBack}
                    className="text-[var(--proto-text-muted)] hover:text-[var(--proto-text)] transition-colors text-sm cursor-pointer"
                >
                    &larr; Back
                </button>
                <span className="text-sm font-semibold text-[var(--proto-text)]">
                    {incident ? incident.title : section?.name}
                </span>
                {incident && (
                    <span
                        className="text-[10px] font-medium px-1.5 py-0.5 rounded capitalize"
                        style={{
                            backgroundColor: `${severityColor[incident.severity]}20`,
                            color: severityColor[incident.severity],
                        }}
                    >
                        {incident.severity}
                    </span>
                )}
            </div>

            <div className="px-5 py-4 flex flex-col gap-5">
                {section && <SectionKPIs section={section} />}
                {incident && <IncidentDetails incident={incident} sections={sections} />}

                {/* Time series chart */}
                <div className="bg-[var(--proto-surface)] rounded-lg border border-[var(--proto-border)] p-4">
                    <h3 className="text-xs font-medium text-[var(--proto-text-muted)] uppercase tracking-wider mb-3">
                        Time Series
                    </h3>
                    <TimeSeriesChart data={timeSeries} />
                </div>

                {/* Data table */}
                <div className="bg-[var(--proto-surface)] rounded-lg border border-[var(--proto-border)] p-4">
                    <h3 className="text-xs font-medium text-[var(--proto-text-muted)] uppercase tracking-wider mb-3">
                        Recent Data
                    </h3>
                    <div className="overflow-x-auto">
                        <table className="w-full text-xs">
                            <thead>
                                <tr className="text-[var(--proto-text-muted)] border-b border-[var(--proto-border)]">
                                    <th className="text-left py-1.5 pr-3 font-medium">Time</th>
                                    <th className="text-right py-1.5 px-3 font-medium">Speed</th>
                                    <th className="text-right py-1.5 px-3 font-medium">Flow</th>
                                    <th className="text-right py-1.5 pl-3 font-medium">Occ.</th>
                                </tr>
                            </thead>
                            <tbody>
                                {timeSeries.slice(-10).map((row, i) => (
                                    <tr
                                        key={i}
                                        className="border-b border-[var(--proto-border)] text-[var(--proto-text-secondary)]"
                                    >
                                        <td className="py-1.5 pr-3">{row.time}</td>
                                        <td className="text-right py-1.5 px-3">
                                            <span style={{ color: getSpeedColor(row.speed) }}>{row.speed}</span> km/h
                                        </td>
                                        <td className="text-right py-1.5 px-3">{row.flow} veh/h</td>
                                        <td className="text-right py-1.5 pl-3">{row.occupancy}%</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>
    )
}

function computeTrend(history: number[]): { delta: number; pct: number; isUp: boolean } {
    const recent = history.slice(-5)
    const earlier = history.slice(0, 5)
    const avgRecent = recent.reduce((a, b) => a + b, 0) / recent.length
    const avgEarlier = earlier.reduce((a, b) => a + b, 0) / earlier.length
    const delta = avgRecent - avgEarlier
    const pct = avgEarlier !== 0 ? Math.round((delta / avgEarlier) * 100) : 0
    return { delta, pct, isUp: delta > 0 }
}

function TrendBadge({ pct, positiveIsGood }: { pct: number; positiveIsGood: boolean }) {
    if (pct === 0) return null
    const isUp = pct > 0
    const isGood = positiveIsGood ? isUp : !isUp
    return (
        <span className={cn('text-[10px] ml-1', isGood ? 'text-green-400' : 'text-red-400')}>
            {isUp ? '\u2191' : '\u2193'}{Math.abs(pct)}%
        </span>
    )
}

function SectionKPIs({ section }: { section: Section }) {
    const speedTrend = computeTrend(section.speedHistory)
    const flowTrend = computeTrend(section.countHistory)

    const fiber = fibers.find((f) => f.id === section.fiberId)

    const kpis = [
        { label: 'Avg Speed', value: `${section.avgSpeed}`, unit: 'km/h', trend: section.speedHistory, color: '#6366f1', trendPct: speedTrend.pct, positiveIsGood: true },
        { label: 'Flow', value: `${section.flow}`, unit: 'veh/h', trend: section.countHistory, color: '#8b5cf6', trendPct: flowTrend.pct, positiveIsGood: true },
        { label: 'Occupancy', value: `${section.occupancy}`, unit: '%', color: '#0ea5e9' },
        { label: 'Travel Time', value: `${section.travelTime}`, unit: 'min', color: fiber?.color ?? '#6366f1' },
    ]

    return (
        <div className="grid grid-cols-2 gap-3">
            {kpis.map((kpi) => (
                <div
                    key={kpi.label}
                    className="bg-[var(--proto-surface)] rounded-lg border border-[var(--proto-border)] p-3"
                >
                    <div className="text-[10px] text-[var(--proto-text-muted)] uppercase tracking-wider mb-1">
                        {kpi.label}
                    </div>
                    <div className="flex items-end justify-between">
                        <div>
                            <span className="text-xl font-semibold text-[var(--proto-text)]">{kpi.value}</span>
                            <span className="text-xs text-[var(--proto-text-muted)] ml-1">{kpi.unit}</span>
                            {kpi.trendPct !== undefined && (
                                <TrendBadge pct={kpi.trendPct} positiveIsGood={kpi.positiveIsGood ?? true} />
                            )}
                        </div>
                        {kpi.trend && (
                            <Sparkline data={kpi.trend} color={kpi.color} width={48} height={20} />
                        )}
                    </div>
                </div>
            ))}
        </div>
    )
}

function IncidentDetails({ incident, sections }: {
    incident: NonNullable<ReturnType<typeof incidents.find>>
    sections: Section[]
}) {
    const relatedSection = sections.find((s) => s.id === incident.sectionId)

    return (
        <div className="flex flex-col gap-3">
            <div className="bg-[var(--proto-surface)] rounded-lg border border-[var(--proto-border)] p-4">
                <div className="text-sm text-[var(--proto-text)] mb-2">{incident.description}</div>
                <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-[var(--proto-text-secondary)]">
                    <span>Type: <span className="capitalize">{incident.type}</span></span>
                    <span>Time: {new Date(incident.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                    <span>Location: {incident.location[1].toFixed(4)}N, {incident.location[0].toFixed(4)}E</span>
                    <span>
                        Status:{' '}
                        <span className={cn(incident.resolved ? 'text-[var(--proto-green)]' : 'text-[var(--proto-red)]')}>
                            {incident.resolved ? 'Resolved' : 'Active'}
                        </span>
                    </span>
                </div>
            </div>

            {relatedSection && (
                <div className="bg-[var(--proto-surface)] rounded-lg border border-[var(--proto-border)] p-4">
                    <h3 className="text-xs font-medium text-[var(--proto-text-muted)] uppercase tracking-wider mb-2">
                        Affected Section
                    </h3>
                    <div className="text-sm text-[var(--proto-text)] mb-1">{relatedSection.name}</div>
                    <div className="flex gap-4 text-xs text-[var(--proto-text-secondary)]">
                        <span>{relatedSection.avgSpeed} km/h</span>
                        <span>{relatedSection.flow} veh/h</span>
                        <span>{relatedSection.occupancy}% occ.</span>
                        <span>Ch {relatedSection.startChannel}-{relatedSection.endChannel}</span>
                    </div>
                </div>
            )}
        </div>
    )
}
