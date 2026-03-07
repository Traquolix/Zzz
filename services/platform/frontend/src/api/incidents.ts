import { apiPaginatedRequest, apiRequest, type PaginatedResponse } from './client'
import type { DataFlow } from '@/context/RealtimeContext'
import type { Incident, IncidentSnapshot, IncidentActionHistory, IncidentAction } from '@/types/incident'

/**
 * Fetch incidents from the paginated endpoint.
 * Returns the full paginated response so callers can check hasMore.
 */
export async function fetchIncidents(): Promise<PaginatedResponse<Incident>> {
  return apiPaginatedRequest<Incident>('/api/incidents')
}

/**
 * Fetch snapshot data for a specific incident.
 */
export async function fetchIncidentSnapshot(incidentId: string, flow?: DataFlow): Promise<IncidentSnapshot> {
  const params = flow ? `?flow=${flow}` : ''
  return apiRequest<IncidentSnapshot>(`/api/incidents/${incidentId}/snapshot${params}`)
}

/**
 * Fetch workflow action history for an incident.
 */
export async function fetchIncidentActions(incidentId: string): Promise<IncidentActionHistory> {
  return apiRequest<IncidentActionHistory>(`/api/incidents/${incidentId}/actions`)
}

/**
 * Post a workflow action (acknowledge, investigate, resolve) for an incident.
 */
export async function postIncidentAction(incidentId: string, action: string, note?: string): Promise<IncidentAction> {
  return apiRequest<IncidentAction>(`/api/incidents/${incidentId}/actions`, {
    method: 'POST',
    body: { action, note: note ?? '' },
  })
}
