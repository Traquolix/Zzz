import { createContext } from 'react'
import type { Map } from 'mapbox-gl'

/**
 * Dashboard-level context for accessing the map instance from any widget.
 * This allows widgets outside the Map component tree to interact with the map.
 */
export type MapInstanceContextType = {
    map: Map | null
    ready: boolean
    setMapInstance: (map: Map | null) => void
}

export const MapInstanceContext = createContext<MapInstanceContextType | null>(null)
