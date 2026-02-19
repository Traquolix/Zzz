import { apiRequest } from './client'
import type { Incident, IncidentSnapshot } from '@/types/incident'

/**
 * Fetch all incidents
 */
export async function fetchIncidents(): Promise<Incident[]> {
    return apiRequest<Incident[]>('/api/incidents')
}

/**
 * Fetch snapshot data for a specific incident
 */
export async function fetchIncidentSnapshot(incidentId: string): Promise<IncidentSnapshot> {
    return apiRequest<IncidentSnapshot>(`/api/incidents/${incidentId}/snapshot`)
}
