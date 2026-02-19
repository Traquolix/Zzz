import { createContext, useContext } from 'react'
import type { MapboxOverlay } from '@deck.gl/mapbox'

type MapContextType = {
    map: mapboxgl.Map
    deckOverlay: MapboxOverlay
}

export const MapContext = createContext<MapContextType | null>(null)

export const useMap = () => {
    const context = useContext(MapContext)
    if (!context) throw new Error('useMap must be used within MapContainer')
    return context.map
}

export const useDeckOverlay = () => {
    const context = useContext(MapContext)
    if (!context) throw new Error('useDeckOverlay must be used within MapContainer')
    return context.deckOverlay
}