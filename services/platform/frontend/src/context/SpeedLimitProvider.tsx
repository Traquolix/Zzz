import { useCallback, useMemo, type ReactNode } from 'react'
import type { SpeedLimitZone } from '@/types/speedLimit'
import type { UserPreferences } from '@/types/user'
import { SpeedLimitContext } from './SpeedLimitContext'
import { usePreferenceMap } from '@/hooks/usePreferenceMap'

function generateZoneId(fiberId: string, startChannel: number, endChannel: number): string {
    return `zone:${fiberId}:${startChannel}-${endChannel}`
}

const preferenceConfig = {
    load: (prefs: UserPreferences) => {
        const zones = prefs?.map?.speedLimitZones
        if (!zones?.length) return null
        return new Map(zones.map(z => [z.id, z]))
    },
    save: (map: Map<string, SpeedLimitZone>, currentPrefs: UserPreferences | null) => ({
        map: {
            ...currentPrefs?.map,
            speedLimitZones: Array.from(map.values()),
        },
    }),
}

export function SpeedLimitProvider({ children }: { children: ReactNode }) {
    // eslint-disable-next-line react-hooks/exhaustive-deps
    const config = useMemo(() => preferenceConfig, [])
    const { map: zones, setMap: setZones, scheduleSave } = usePreferenceMap(config)

    const addZone = useCallback((
        fiberId: string,
        startChannel: number,
        endChannel: number,
        limit: number,
    ) => {
        const start = Math.min(startChannel, endChannel)
        const end = Math.max(startChannel, endChannel)
        const id = generateZoneId(fiberId, start, end)

        const zone: SpeedLimitZone = { id, fiberId, startChannel: start, endChannel: end, limit }

        setZones(prev => {
            const next = new Map(prev)
            next.set(id, zone)
            scheduleSave(next)
            return next
        })
    }, [setZones, scheduleSave])

    const updateZone = useCallback((
        zoneId: string,
        updates: Partial<Pick<SpeedLimitZone, 'startChannel' | 'endChannel' | 'limit'>>,
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
                limit: newLimit,
            })

            scheduleSave(next)
            return next
        })
    }, [setZones, scheduleSave])

    const deleteZone = useCallback((zoneId: string) => {
        setZones(prev => {
            const next = new Map(prev)
            next.delete(zoneId)
            scheduleSave(next)
            return next
        })
    }, [setZones, scheduleSave])

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
            getZonesForFiber,
        }}>
            {children}
        </SpeedLimitContext.Provider>
    )
}
