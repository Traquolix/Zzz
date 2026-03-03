import { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { useIncidents } from '@/hooks/useIncidents'
import { useKeyboardShortcut } from '@/hooks/useKeyboardShortcuts'
import { IncidentTimeline, IncidentDetailPanel } from '@/components/IncidentTimeline'
import { Download, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { SearchInput } from '@/components/ui/SearchInput'
import { EmptyState } from '@/components/ui/EmptyState'
import { Skeleton } from '@/components/ui/Skeleton'
import { downloadCSV } from '@/lib/csvExport'
import type { Incident } from '@/types/incident'

export function Incidents() {
    const { incidents, loading, isNewIncident, updateIncidentStatus } = useIncidents()
    const [selectedIncident, setSelectedIncident] = useState<Incident | null>(null)
    const [searchQuery, setSearchQuery] = useState('')
    const containerRef = useRef<HTMLDivElement>(null)
    const { t } = useTranslation()

    // Filter incidents based on search query
    const filteredIncidents = useMemo(() => {
        if (!searchQuery.trim()) return incidents

        const query = searchQuery.toLowerCase()
        return incidents.filter(incident =>
            incident.fiberLine.toLowerCase().includes(query) ||
            incident.type.toLowerCase().includes(query) ||
            incident.severity.toLowerCase().includes(query) ||
            incident.id.toLowerCase().includes(query)
        )
    }, [incidents, searchQuery])

    // Handle click outside to close panel
    useEffect(() => {
        const handleClickOutside = (e: MouseEvent) => {
            if (!selectedIncident) return

            const target = e.target as HTMLElement

            const isOnDetailPanel = target.closest('[data-detail-panel]')
            const isOnTimelineCard = target.closest('[data-timeline-card]')

            if (!isOnDetailPanel && !isOnTimelineCard) {
                setSelectedIncident(null)
            }
        }

        document.addEventListener('mousedown', handleClickOutside)
        return () => document.removeEventListener('mousedown', handleClickOutside)
    }, [selectedIncident])

    // Handle escape key to close detail panel
    useKeyboardShortcut({
        combo: 'Escape',
        handler: () => {
            if (selectedIncident) {
                setSelectedIncident(null)
            }
        },
        global: true,
    })

    const handleSelectIncident = (incident: Incident) => {
        setSelectedIncident(prev =>
            prev?.id === incident.id ? null : incident
        )
    }

    const handleExportCSV = useCallback(() => {
        const columns = [
            { header: t('incidents.csvHeaders.id'), accessor: (r: Incident) => r.id },
            { header: t('incidents.csvHeaders.type'), accessor: (r: Incident) => r.type },
            { header: t('incidents.csvHeaders.severity'), accessor: (r: Incident) => r.severity },
            { header: t('incidents.csvHeaders.fiber'), accessor: (r: Incident) => r.fiberLine },
            { header: t('incidents.csvHeaders.channel'), accessor: (r: Incident) => r.channel },
            { header: t('incidents.csvHeaders.detectedAt'), accessor: (r: Incident) => r.detectedAt },
            { header: t('incidents.csvHeaders.status'), accessor: (r: Incident) => r.status },
            { header: t('incidents.csvHeaders.duration'), accessor: (r: Incident) => r.duration ?? '' },
        ]
        const timestamp = new Date().toISOString().slice(0, 10)
        downloadCSV(columns, incidents, `incidents-${timestamp}.csv`)
    }, [incidents, t])

    return (
        <div ref={containerRef} className="h-full relative overflow-hidden">
            {/* ARIA live region for announcement of incident count */}
            <div role="status" aria-live="polite" className="sr-only">
                {incidents.length > 0
                    ? t('incidents.count', { count: filteredIncidents.length })
                    : t('incidents.noIncidents')
                }
            </div>

            {/* Timeline section - always full width, content shifts on desktop only */}
            <div
                className={`absolute inset-0 overflow-auto transition-all duration-300 ease-out ${
                    selectedIncident ? 'md:right-2/5 lg:right-1/2' : 'right-0'
                }`}
            >
                <div className="max-w-3xl mx-auto py-8 px-4">
                    <div className="flex items-center justify-between mb-6">
                        <h1 className="text-2xl font-semibold text-slate-900">
                            {t('incidents.title')}
                        </h1>
                        {incidents.length > 0 && (
                            <Button
                                variant="outline"
                                size="sm"
                                onClick={handleExportCSV}
                                aria-label={t('incidents.export')}
                            >
                                <Download className="h-4 w-4 mr-1.5" aria-hidden="true" />
                                {t('incidents.export')}
                            </Button>
                        )}
                    </div>

                    {loading ? (
                        <div className="flex items-center justify-center h-64" role="status">
                            <Skeleton lines={5} className="w-full" />
                            <span className="sr-only">{t('common.loading')}</span>
                        </div>
                    ) : incidents.length === 0 ? (
                        <EmptyState
                            title={t('incidents.empty')}
                            description={t('incidents.emptyDescription')}
                        />
                    ) : (
                        <>
                            <div className="mb-6">
                                <SearchInput
                                    value={searchQuery}
                                    onChange={setSearchQuery}
                                    placeholder={t('incidents.searchPlaceholder', 'Search incidents...')}
                                />
                            </div>

                            {filteredIncidents.length === 0 ? (
                                <EmptyState
                                    title={t('incidents.empty')}
                                    description={t('incidents.emptyDescription')}
                                />
                            ) : (
                                <div data-timeline-card>
                                    <IncidentTimeline
                                        incidents={filteredIncidents}
                                        selectedIncidentId={selectedIncident?.id}
                                        onSelectIncident={handleSelectIncident}
                                        isNewIncident={isNewIncident}
                                    />
                                </div>
                            )}
                        </>
                    )}
                </div>
            </div>

            {/* Backdrop overlay - mobile only */}
            {selectedIncident && (
                <div
                    className="fixed inset-0 bg-black/30 md:hidden z-[999]"
                    onClick={() => setSelectedIncident(null)}
                />
            )}

            {/* Detail panel - responsive: fixed bottom sheet on mobile, side panel on desktop */}
            <div
                data-detail-panel
                className={`fixed md:absolute top-0 md:top-0 bottom-0 md:bottom-0 right-0 md:right-0 inset-x-0 md:inset-auto h-[85vh] md:h-auto md:rounded-none rounded-t-xl md:w-2/5 lg:w-1/2 bg-white dark:bg-slate-900 border-l border-slate-200 dark:border-slate-700 transition-transform duration-300 ease-out z-[1000] md:z-auto ${
                    selectedIncident ? 'translate-y-0 md:translate-x-0' : 'translate-y-full md:translate-x-full'
                }`}
            >
                {selectedIncident && (
                    <>
                        {/* Mobile drag handle - visible only on mobile */}
                        <div className="md:hidden flex justify-center pt-2 pb-1">
                            <div className="w-12 h-1 rounded-full bg-slate-300" />
                        </div>

                        {/* Mobile close button - visible only on mobile */}
                        <button
                            onClick={() => setSelectedIncident(null)}
                            className="md:hidden absolute top-12 right-4 p-2 text-slate-400 hover:text-slate-600 hover:bg-slate-100 rounded-lg transition-colors z-10"
                            aria-label={t('incidents.closeDetail')}
                        >
                            <X className="h-5 w-5" aria-hidden="true" />
                        </button>

                        <IncidentDetailPanel
                            incident={selectedIncident}
                            onClose={() => setSelectedIncident(null)}
                            onStatusChange={updateIncidentStatus}
                        />
                    </>
                )}
            </div>
        </div>
    )
}
