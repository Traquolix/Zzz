import { apiRequest, ApiError } from './client'

export type TechStats = {
    fiberCount: number
    totalChannels: number
    activeVehicles: number
    detectionsPerSecond: number
    activeIncidents: number
    systemUptime: number
}

const STAT_KEYS: (keyof TechStats)[] = [
    'fiberCount', 'totalChannels', 'activeVehicles',
    'detectionsPerSecond', 'activeIncidents', 'systemUptime',
]

/**
 * Fetch system tech stats with runtime type validation.
 */
export async function fetchStats(): Promise<TechStats> {
    const raw = await apiRequest<unknown>('/api/stats')
    if (!raw || typeof raw !== 'object') {
        throw new ApiError(0, 'Invalid stats response shape')
    }
    const obj = raw as Record<string, unknown>
    for (const key of STAT_KEYS) {
        if (typeof obj[key] !== 'number') {
            throw new ApiError(0, `Invalid stats field: ${key}`)
        }
    }
    return raw as TechStats
}
