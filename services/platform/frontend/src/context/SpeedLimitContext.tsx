import { createContext } from 'react'
import type { SpeedLimitZone } from '@/types/speedLimit'

export type SpeedLimitContextType = {
    zones: Map<string, SpeedLimitZone>
    addZone: (fiberId: string, startChannel: number, endChannel: number, limit: number) => void
    updateZone: (zoneId: string, updates: Partial<Pick<SpeedLimitZone, 'startChannel' | 'endChannel' | 'limit'>>) => void
    deleteZone: (zoneId: string) => void
    getZonesForFiber: (fiberId: string) => SpeedLimitZone[]
}

export const SpeedLimitContext = createContext<SpeedLimitContextType | null>(null)
