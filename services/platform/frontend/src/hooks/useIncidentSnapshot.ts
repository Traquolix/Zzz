import { useState, useCallback } from 'react'
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
    const [snapshot, setSnapshot] = useState<IncidentSnapshot | null>(null)
    const [loading, setLoading] = useState(false)
    const [error, setError] = useState<string | null>(null)

    const fetchSnapshotFn = useCallback(async (incidentId: string) => {
        setLoading(true)
        setError(null)

        try {
            const data = await fetchIncidentSnapshot(incidentId)
            setSnapshot(data)
        } catch (e) {
            if (e instanceof ApiError && e.status === 404) {
                setError('No snapshot available for this incident')
            } else {
                setError('Failed to fetch snapshot')
            }
            setSnapshot(null)
        } finally {
            setLoading(false)
        }
    }, [])

    const clearSnapshot = useCallback(() => {
        setSnapshot(null)
        setError(null)
    }, [])

    return { snapshot, loading, error, fetchSnapshot: fetchSnapshotFn, clearSnapshot }
}
