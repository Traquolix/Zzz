import { useState, useCallback, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import type { IncidentSnapshot } from '@/types/incident'
import { fetchIncidentSnapshot } from '@/api/incidents'
import { ApiError } from '@/api/client'

type UseIncidentSnapshotResult = {
    snapshot: IncidentSnapshot | null
    loading: boolean
    error: string | null
    fetchSnapshot: (incidentId: string) => Promise<void>
    clearSnapshot: () => void
}

export function useIncidentSnapshot(): UseIncidentSnapshotResult {
    const { t } = useTranslation()
    const [snapshot, setSnapshot] = useState<IncidentSnapshot | null>(null)
    const [loading, setLoading] = useState(false)
    const [error, setError] = useState<string | null>(null)
    // Track the latest request to ignore stale responses
    const requestIdRef = useRef(0)

    const fetchSnapshotFn = useCallback(async (incidentId: string) => {
        const thisRequest = ++requestIdRef.current

        setLoading(true)
        setError(null)

        try {
            const data = await fetchIncidentSnapshot(incidentId)
            if (thisRequest === requestIdRef.current) {
                setSnapshot(data)
            }
        } catch (e) {
            if (thisRequest !== requestIdRef.current) return
            if (e instanceof ApiError && e.status === 404) {
                setError(t('common.noSnapshot'))
            } else if (e instanceof ApiError || typeof e === 'object') {
                setError(t('common.somethingWentWrong'))
            }
            setSnapshot(null)
        } finally {
            if (thisRequest === requestIdRef.current) {
                setLoading(false)
            }
        }

    }, [t])

    const clearSnapshot = useCallback(() => {
        setSnapshot(null)
        setError(null)
    }, [])

    return { snapshot, loading, error, fetchSnapshot: fetchSnapshotFn, clearSnapshot }
}
