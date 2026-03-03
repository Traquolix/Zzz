import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { showToast } from '@/lib/toast'
import { postIncidentAction, fetchIncidentActions } from '@/api/incidents'
import type { Incident, IncidentStatus, IncidentAction } from '@/types/incident'
import { Loader2 } from 'lucide-react'

const VALID_TRANSITIONS: Record<IncidentStatus, IncidentStatus[]> = {
    active: ['acknowledged', 'investigating', 'resolved'],
    acknowledged: ['investigating', 'resolved'],
    investigating: ['resolved'],
    resolved: [],
}

const ACTION_STYLES: Record<string, string> = {
    acknowledged: 'bg-blue-600 hover:bg-blue-700 text-white',
    investigating: 'bg-amber-600 hover:bg-amber-700 text-white',
    resolved: 'bg-emerald-600 hover:bg-emerald-700 text-white',
}

type Props = {
    incident: Incident
    onStatusChange: (incidentId: string, newStatus: IncidentStatus) => void
}

export function IncidentActionBar({ incident, onStatusChange }: Props) {
    const { t } = useTranslation()
    const [submitting, setSubmitting] = useState(false)
    const [showNote, setShowNote] = useState(false)
    const [note, setNote] = useState('')
    const [history, setHistory] = useState<IncidentAction[]>([])
    const [historyLoading, setHistoryLoading] = useState(true)

    const transitions = VALID_TRANSITIONS[incident.status] || []

    useEffect(() => {
        let cancelled = false
        setHistoryLoading(true)
        fetchIncidentActions(incident.id)
            .then(data => {
                if (!cancelled) setHistory(data.actions)
            })
            .catch(() => {
                if (!cancelled) setHistory([])
            })
            .finally(() => {
                if (!cancelled) setHistoryLoading(false)
            })
        return () => { cancelled = true }
    }, [incident.id, incident.status])

    const handleAction = async (targetStatus: IncidentStatus) => {
        setSubmitting(true)
        try {
            await postIncidentAction(incident.id, targetStatus, note || undefined)
            onStatusChange(incident.id, targetStatus)
            setNote('')
            setShowNote(false)
            showToast.success(t('incidents.actions.statusChanged'))
        } catch {
            showToast.error(t('common.error'))
        } finally {
            setSubmitting(false)
        }
    }

    if (transitions.length === 0 && history.length === 0) return null

    return (
        <div className="mt-4 space-y-3">
            {/* Action buttons */}
            {transitions.length > 0 && (
                <div className="space-y-2">
                    <div className="flex items-center gap-2">
                        {transitions.map(target => (
                            <button
                                key={target}
                                onClick={() => handleAction(target)}
                                disabled={submitting}
                                className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1 ${ACTION_STYLES[target] || 'bg-slate-600 hover:bg-slate-700 text-white'}`}
                            >
                                {submitting && <Loader2 className="h-3 w-3 animate-spin" />}
                                {t(`incidents.actions.${target}`)}
                            </button>
                        ))}
                        {!showNote && (
                            <button
                                onClick={() => setShowNote(true)}
                                className="px-3 py-1.5 text-xs text-slate-500 hover:text-slate-700"
                            >
                                {t('incidents.actions.addNote')}
                            </button>
                        )}
                    </div>
                    {showNote && (
                        <input
                            type="text"
                            value={note}
                            onChange={e => setNote(e.target.value)}
                            placeholder={t('incidents.actions.notePlaceholder')}
                            className="w-full border border-slate-300 rounded-lg px-3 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-blue-500"
                        />
                    )}
                </div>
            )}

            {/* Action history */}
            {!historyLoading && history.length > 0 && (
                <div className="border-t border-slate-100 pt-3">
                    <p className="text-[10px] uppercase tracking-wider text-slate-400 font-medium mb-2">
                        {t('incidents.actions.history')}
                    </p>
                    <div className="space-y-1.5">
                        {history.map(action => (
                            <div key={action.id} className="flex items-center gap-2 text-xs text-slate-500">
                                <span className="font-medium text-slate-600">{action.fromStatus}</span>
                                <span>→</span>
                                <span className="font-medium text-slate-600">{action.toStatus}</span>
                                {action.note && (
                                    <span className="text-slate-400 truncate max-w-[150px]" title={action.note}>
                                        — {action.note}
                                    </span>
                                )}
                                <span className="text-slate-300 ml-auto text-[10px]">
                                    {new Date(action.performedAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                                </span>
                            </div>
                        ))}
                    </div>
                </div>
            )}
        </div>
    )
}
