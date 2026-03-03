import { useEffect, useState, useRef, useCallback } from 'react'
import { useRealtime } from '@/hooks/useRealtime'
import type { Incident, IncidentStatus } from '@/types/incident'
import { fetchIncidents } from '@/api/incidents'
import { parseIncident } from '@/lib/parseMessage'
import { logger } from '@/lib/logger'

// Time in ms to consider an incident as "new" (shows indicator)
const NEW_INCIDENT_DURATION = 30_000

export function useIncidents() {
    const { subscribe, connected } = useRealtime()
    const [incidents, setIncidents] = useState<Incident[]>([])
    const [loading, setLoading] = useState(true)
    // Track when incidents were received client-side (for "new" indicator)
    const receivedAtRef = useRef<Map<string, number>>(new Map())
    // Force re-render when "new" status expires
    const [, forceUpdate] = useState(0)

    // Check if an incident is "new" (received recently via WebSocket)
    const isNewIncident = useCallback((incidentId: string) => {
        const receivedAt = receivedAtRef.current.get(incidentId)
        if (!receivedAt) return false
        return Date.now() - receivedAt < NEW_INCIDENT_DURATION
    }, [])

    // Update incident status locally
    const updateIncidentStatus = useCallback((id: string, status: IncidentStatus) => {
        setIncidents(prev => prev.map(i => i.id === id ? { ...i, status } : i))
    }, [])

    useEffect(() => {
        let mounted = true

        fetchIncidents()
            .then(response => {
                if (mounted) {
                    setIncidents(response.results)
                    setLoading(false)
                }
            })
            .catch(err => {
                if (mounted) {
                    logger.error('Failed to fetch incidents:', err)
                    setLoading(false)
                }
            })

        return () => {
            mounted = false
        }
    }, [])

    useEffect(() => {
        if (!connected) return

        return subscribe('incidents', (data) => {
            const incident = parseIncident(data)
            if (!incident) return
            setIncidents(prev => {
                const existsIdx = prev.findIndex(i => i.id === incident.id)
                if (existsIdx >= 0) {
                    // Update existing incident (e.g., status changed to resolved)
                    const next = [...prev]
                    next[existsIdx] = incident
                    return next
                }
                // New incident - track when it was received
                receivedAtRef.current.set(incident.id, Date.now())
                return [incident, ...prev]
            })
        })
    }, [connected, subscribe])

    // Auto-expire "new" indicators
    useEffect(() => {
        const interval = setInterval(() => {
            const now = Date.now()
            let hasExpired = false
            receivedAtRef.current.forEach((receivedAt, id) => {
                if (now - receivedAt >= NEW_INCIDENT_DURATION) {
                    receivedAtRef.current.delete(id)
                    hasExpired = true
                }
            })
            if (hasExpired) {
                forceUpdate(n => n + 1)
            }
        }, 5000)
        return () => clearInterval(interval)
    }, [])

    return { incidents, loading, connected, isNewIncident, updateIncidentStatus }
}