import { apiPaginatedRequest, apiRequest, type PaginatedResponse } from './client'
import type { DataFlow } from '@/context/RealtimeContext'
import type { Incident, IncidentSnapshot, IncidentActionHistory, IncidentAction } from '@/types/incident'

/**
 * Fetch incidents from the paginated endpoint.
 * Optionally filter by date (YYYY-MM-DD) for calendar browsing.
 */
export async function fetchIncidents(flow?: DataFlow, date?: string): Promise<PaginatedResponse<Incident>> {
  const params = new URLSearchParams()
  if (flow) params.set('flow', flow)
  if (date) params.set('date', date)
  const qs = params.toString()
  return apiPaginatedRequest<Incident>(`/api/incidents${qs ? '?' + qs : ''}`)
}

import type { CalendarDay } from '@/types/incident'

/**
 * Fetch daily incident counts for a month (YYYY-MM).
 */
export async function fetchIncidentCalendar(month: string, flow?: DataFlow): Promise<CalendarDay[]> {
  const params = new URLSearchParams({ month })
  if (flow) params.set('flow', flow)
  const res = await apiRequest<{ days: CalendarDay[] }>(`/api/incidents/calendar?${params}`)
  return res.days
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
