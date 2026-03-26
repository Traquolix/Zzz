import { useEffect, useState, useRef, useCallback } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useRealtime } from '@/hooks/useRealtime'
import { useFlowReset } from '@/hooks/useFlowReset'
import type { Incident, IncidentStatus } from '@/types/incident'
import { fetchIncidents } from '@/api/incidents'
import { parseIncident } from '@/lib/parseMessage'

// Time in ms to consider an incident as "new" (shows indicator)
const NEW_INCIDENT_DURATION = 30_000

export function useIncidents() {
  const { subscribe, connected, flow } = useRealtime()
  const queryClient = useQueryClient()
  // Track when incidents were received client-side (for "new" indicator)
  const receivedAtRef = useRef<Map<string, number>>(new Map())
  // Force re-render when "new" status expires
  const [, forceUpdate] = useState(0)

  const { data: incidents = [], isLoading: loading } = useQuery({
    queryKey: ['incidents', flow],
    queryFn: async () => {
      const response = await fetchIncidents(flow)
      return response.results
    },
    staleTime: 60_000,
  })

  // Clear accumulated state on flow switch (backend re-sends initial incidents)
  useFlowReset(() => {
    queryClient.removeQueries({ queryKey: ['incidents'] })
    receivedAtRef.current.clear()
  })

  // Check if an incident is "new" (received recently via WebSocket)
  const isNewIncident = useCallback((incidentId: string) => {
    const receivedAt = receivedAtRef.current.get(incidentId)
    if (!receivedAt) return false
    return Date.now() - receivedAt < NEW_INCIDENT_DURATION
  }, [])

  // Update incident status locally
  const updateIncidentStatus = useCallback(
    (id: string, status: IncidentStatus) => {
      queryClient.setQueryData<Incident[]>(['incidents', flow], prev =>
        (prev ?? []).map(i => (i.id === id ? { ...i, status } : i)),
      )
    },
    [queryClient, flow],
  )

  // WebSocket subscription — apply real-time updates to the query cache
  useEffect(() => {
    if (!connected) return

    return subscribe('incidents', data => {
      const incident = parseIncident(data)
      if (!incident) return

      queryClient.setQueryData<Incident[]>(['incidents', flow], prev => {
        const list = prev ?? []
        const existsIdx = list.findIndex(i => i.id === incident.id)
        if (existsIdx >= 0) {
          const next = [...list]
          next[existsIdx] = incident
          return next
        }
        // New incident — track when it was received
        receivedAtRef.current.set(incident.id, Date.now())
        return [incident, ...list]
      })
    })
  }, [connected, subscribe, queryClient, flow])

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
