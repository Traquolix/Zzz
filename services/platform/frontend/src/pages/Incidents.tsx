import { useState, useEffect, useRef, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { useIncidents } from '@/hooks/useIncidents'
import { IncidentTimeline, IncidentDetailPanel } from '@/components/IncidentTimeline'
import { Loader2, Download } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { downloadCSV } from '@/lib/csvExport'
import type { Incident } from '@/types/incident'

export function Incidents() {
    const { incidents, loading, isNewIncident } = useIncidents()
    const [selectedIncident, setSelectedIncident] = useState<Incident | null>(null)
    const containerRef = useRef<HTMLDivElement>(null)
    const { t } = useTranslation()

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

    // Handle escape key to close
    useEffect(() => {
        const handleKeyDown = (e: KeyboardEvent) => {
            if (e.key === 'Escape' && selectedIncident) {
                setSelectedIncident(null)
            }
        }

        document.addEventListener('keydown', handleKeyDown)
        return () => document.removeEventListener('keydown', handleKeyDown)
    }, [selectedIncident])

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
            {/* Timeline section - always full width, content shifts left */}
            <div
                className={`absolute inset-0 overflow-auto transition-all duration-300 ease-out ${
                    selectedIncident ? 'right-1/2' : 'right-0'
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
                            <Loader2 className="h-8 w-8 animate-spin text-slate-400" aria-hidden="true" />
                            <span className="sr-only">{t('common.loading')}</span>
                        </div>
                    ) : (
                        <div data-timeline-card>
                            <IncidentTimeline
                                incidents={incidents}
                                selectedIncidentId={selectedIncident?.id}
                                onSelectIncident={handleSelectIncident}
                                isNewIncident={isNewIncident}
                            />
                        </div>
                    )}
                </div>
            </div>

            {/* Detail panel - slides in from right */}
            <div
                data-detail-panel
                className={`absolute top-0 bottom-0 right-0 w-1/2 bg-white border-l border-slate-200 transition-transform duration-300 ease-out ${
                    selectedIncident ? 'translate-x-0' : 'translate-x-full'
                }`}
            >
                {selectedIncident && (
                    <IncidentDetailPanel
                        incident={selectedIncident}
                        onClose={() => setSelectedIncident(null)}
                    />
                )}
            </div>
        </div>
    )
}
