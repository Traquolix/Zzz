import { apiRequest } from './client'

export type TechStats = {
    fiberCount: number
    totalChannels: number
    activeVehicles: number
    detectionsPerSecond: number
    activeIncidents: number
    systemUptime: number
}

/**
 * Fetch system tech stats
 */
export async function fetchStats(): Promise<TechStats> {
    return apiRequest<TechStats>('/api/stats')
}
