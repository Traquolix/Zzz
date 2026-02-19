import { createContext } from 'react'
import type { Infrastructure, FrequencyReading } from '@/types/infrastructure'

/**
 * Context for infrastructure data (bridges, tunnels).
 * Infrastructure is static/read-only - defined on the server.
 * Selection state is managed by MapSelectionContext.
 */
export type InfrastructureDataContextType = {
    // Infrastructure data (static from server)
    infrastructures: Infrastructure[]
    loading: boolean

    // Latest frequency readings (real-time from WebSocket)
    latestReadings: Map<string, FrequencyReading>  // keyed by infrastructureId
}

export const InfrastructureDataContext = createContext<InfrastructureDataContextType | null>(null)
