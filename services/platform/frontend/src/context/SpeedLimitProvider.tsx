import { useState, useCallback, useEffect, type ReactNode } from 'react'
import type { SpeedLimitZone } from '@/types/speedLimit'
import { SpeedLimitContext } from './SpeedLimitContext'
import { useUserPreferences } from '@/hooks/useUserPreferences'
import { useDebouncedSync } from '@/hooks/useDebouncedSync'

function generateZoneId(fiberId: string, startChannel: number, endChannel: number): string {
    return `zone:${fiberId}:${startChannel}-${endChannel}`
}

function zonesToMap(zones: SpeedLimitZone[]): Map<string, SpeedLimitZone> {
    return new Map(zones.map(z => [z.id, z]))
}

function mapToZones(zonesMap: Map<string, SpeedLimitZone>): SpeedLimitZone[] {
    return Array.from(zonesMap.values())
}

export function SpeedLimitProvider({ children }: { children: ReactNode }) {
    const { preferences, updatePreferences, isLoading: prefsLoading } = useUserPreferences()
    const [zones, setZones] = useState<Map<string, SpeedLimitZone>>(new Map())
    const [initialized, setInitialized] = useState(false)

    // Load from preferences once available
    useEffect(() => {
        if (prefsLoading || initialized) return
        setInitialized(true)

        const savedZones = preferences?.map?.speedLimitZones
        if (savedZones?.length) {
            setZones(zonesToMap(savedZones))
        }
    }, [prefsLoading, preferences, initialized])

    // Debounced save to preferences
    const scheduleSync = useDebouncedSync(
        useCallback((newZones: Map<string, SpeedLimitZone>) => {
            updatePreferences({
                ...preferences,
                map: {
                    ...preferences?.map,
                    speedLimitZones: mapToZones(newZones)
                }
            })
        }, [preferences, updatePreferences])
    )

    const addZone = useCallback((
        fiberId: string,
        startChannel: number,
        endChannel: number,
        limit: number
    ) => {
        const start = Math.min(startChannel, endChannel)
        const end = Math.max(startChannel, endChannel)
        const id = generateZoneId(fiberId, start, end)

        const zone: SpeedLimitZone = {
            id,
            fiberId,
            startChannel: start,
            endChannel: end,
            limit
        }

        setZones(prev => {
            const next = new Map(prev)
            next.set(id, zone)
            scheduleSync(next)
            return next
        })
    }, [scheduleSync])

    const updateZone = useCallback((
        zoneId: string,
        updates: Partial<Pick<SpeedLimitZone, 'startChannel' | 'endChannel' | 'limit'>>
    ) => {
        setZones(prev => {
            const zone = prev.get(zoneId)
            if (!zone) return prev

            const newStart = updates.startChannel ?? zone.startChannel
            const newEnd = updates.endChannel ?? zone.endChannel
            const newLimit = updates.limit ?? zone.limit

            const needsNewId = updates.startChannel !== undefined || updates.endChannel !== undefined
            const newId = needsNewId
                ? generateZoneId(zone.fiberId, Math.min(newStart, newEnd), Math.max(newStart, newEnd))
                : zoneId

            const next = new Map(prev)

            if (needsNewId && newId !== zoneId) {
                next.delete(zoneId)
            }

            next.set(newId, {
                ...zone,
                id: newId,
                startChannel: Math.min(newStart, newEnd),
                endChannel: Math.max(newStart, newEnd),
                limit: newLimit
            })

            scheduleSync(next)
            return next
        })
    }, [scheduleSync])

    const deleteZone = useCallback((zoneId: string) => {
        setZones(prev => {
            const next = new Map(prev)
            next.delete(zoneId)
            scheduleSync(next)
            return next
        })
    }, [scheduleSync])

    const getZonesForFiber = useCallback((fiberId: string): SpeedLimitZone[] => {
        return Array.from(zones.values())
            .filter(z => z.fiberId === fiberId)
            .sort((a, b) => a.startChannel - b.startChannel)
    }, [zones])

    return (
        <SpeedLimitContext.Provider value={{
            zones,
            addZone,
            updateZone,
            deleteZone,
            getZonesForFiber
        }}>
            {children}
        </SpeedLimitContext.Provider>
    )
}
