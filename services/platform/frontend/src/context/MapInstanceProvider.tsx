import { useState, useCallback, useMemo, type ReactNode } from 'react'
import type { Map } from 'mapbox-gl'
import { MapInstanceContext, type MapInstanceContextType } from './MapInstanceContext'

type Props = {
    children: ReactNode
}

/**
 * Provider for dashboard-level map instance access.
 * The Map widget registers its instance here when ready.
 */
export function MapInstanceProvider({ children }: Props) {
    const [map, setMap] = useState<Map | null>(null)

    const setMapInstance = useCallback((instance: Map | null) => {
        setMap(instance)
    }, [])

    const value: MapInstanceContextType = useMemo(() => ({
        map,
        ready: map !== null,
        setMapInstance
    }), [map, setMapInstance])

    return (
        <MapInstanceContext.Provider value={value}>
            {children}
        </MapInstanceContext.Provider>
    )
}
