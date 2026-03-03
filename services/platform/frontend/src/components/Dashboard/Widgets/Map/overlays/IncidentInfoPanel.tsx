import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { useMapSelection } from '@/hooks/useMapSelection'
import { useFibers } from '@/hooks/useFibers'
import { useDashboardState } from '@/context/DashboardContext'
import { SEVERITY_BADGE, INCIDENT_TYPE_LABELS } from '@/constants/incidents'

const SEVERITY_COLORS = SEVERITY_BADGE
const TYPE_LABELS = INCIDENT_TYPE_LABELS

export function IncidentInfoPanel() {
    const { t } = useTranslation()
    const { selectedIncident, selectIncident } = useMapSelection()
    const { fibers } = useFibers()
    const { ownership } = useDashboardState()

    const fiber = useMemo(() => {
        if (!selectedIncident) return null
        return fibers.find(f => f.id === selectedIncident.fiberLine)
    }, [selectedIncident, fibers])

    // Visibility controlled by ownership
    if (!ownership.incidentInfo) return null
    if (!selectedIncident) return null

    const colors = SEVERITY_COLORS[selectedIncident.severity] || SEVERITY_COLORS.low

    return (
        <div className="absolute top-3 md:right-[60px] right-2 bg-white rounded-lg p-3 shadow-lg text-[13px] z-[1000] min-w-[220px] pointer-events-auto max-h-[calc(100vh-8rem)] md:max-h-none overflow-y-auto">
            <div className="flex justify-between items-center mb-2">
                <div className="flex items-center gap-2">
                    <span className={`px-2 py-0.5 rounded text-xs font-semibold uppercase ${colors.bg} ${colors.text}`}>
                        {selectedIncident.severity}
                    </span>
                    <strong className="text-slate-700">
                        {TYPE_LABELS[selectedIncident.type] || selectedIncident.type}
                    </strong>
                </div>
                <button
                    onClick={() => selectIncident(null)}
                    className="bg-transparent border-none cursor-pointer text-slate-400 text-base min-w-[44px] min-h-[44px] md:min-w-0 md:min-h-0 flex items-center justify-center p-0 leading-none hover:text-slate-600"
                    aria-label={t('map.incident.closePanel')}
                >
                    x
                </button>
            </div>

            <div className="text-slate-500 leading-[1.8]">
                <div>
                    <span className="text-slate-400">{`${t('common.fiber')}: `}</span>
                    {fiber?.name || selectedIncident.fiberLine}
                </div>
                <div>
                    <span className="text-slate-400">{`${t('common.channel')}: `}</span>
                    {selectedIncident.channel}
                </div>
                <div>
                    <span className="text-slate-400">{`${t('common.position')}: `}</span>
                    {selectedIncident.lat.toFixed(5)}, {selectedIncident.lng.toFixed(5)}
                </div>
            </div>
        </div>
    )
}
