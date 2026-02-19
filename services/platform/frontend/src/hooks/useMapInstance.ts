import { useContext, useCallback } from 'react'
import mapboxgl from 'mapbox-gl'
import { MapInstanceContext } from '@/context/MapInstanceContext'
import { SectionDataContext } from '@/context/SectionContext'
import { useDashboardState } from '@/context/DashboardContext'
import type { LayerVisibility } from '@/types/section'

/**
 * Hook to access the map instance from any dashboard widget.
 * Returns null if map is not ready yet.
 *
 * Provides layer-aware navigation functions that automatically enable
 * the corresponding layer before flying to a location.
 */
export function useMapInstance() {
    const context = useContext(MapInstanceContext)
    if (!context) {
        throw new Error('useMapInstance must be used within MapInstanceProvider')
    }

    const sectionContext = useContext(SectionDataContext)
    const { hasWidgetType } = useDashboardState()

    const { map, ready } = context
    const layerVisibility = sectionContext?.layerVisibility
    const setLayerVisibility = sectionContext?.setLayerVisibility

    // Fly to a specific point
    const flyTo = useCallback((lng: number, lat: number, zoom = 16, duration = 2000) => {
        if (!map) return
        map.flyTo({
            center: [lng, lat],
            zoom,
            duration
        })
    }, [map])

    // Fit bounds to encompass coordinates
    const fitBounds = useCallback((coordinates: [number, number][], padding = 50, duration = 2000) => {
        if (!map || coordinates.length === 0) return

        const bounds = new mapboxgl.LngLatBounds(coordinates[0], coordinates[0])
        for (const coord of coordinates) {
            bounds.extend(coord)
        }

        map.fitBounds(bounds, {
            padding,
            duration
        })
    }, [map])

    // Enable a layer if map widget is present and layer is off
    const ensureLayerVisible = useCallback((layer: keyof LayerVisibility) => {
        if (!hasWidgetType('map') || !layerVisibility || !setLayerVisibility) return
        if (!layerVisibility[layer]) {
            setLayerVisibility({ ...layerVisibility, [layer]: true })
        }
    }, [hasWidgetType, layerVisibility, setLayerVisibility])

    // Fly to point with layer auto-enable
    const flyToWithLayer = useCallback((
        lng: number,
        lat: number,
        layer: keyof LayerVisibility,
        zoom = 16,
        duration = 2000
    ) => {
        ensureLayerVisible(layer)
        flyTo(lng, lat, zoom, duration)
    }, [ensureLayerVisible, flyTo])

    // Fit bounds with layer auto-enable
    const fitBoundsWithLayer = useCallback((
        coordinates: [number, number][],
        layer: keyof LayerVisibility,
        padding = 50,
        duration = 2000
    ) => {
        ensureLayerVisible(layer)
        fitBounds(coordinates, padding, duration)
    }, [ensureLayerVisible, fitBounds])

    return {
        map,
        ready,
        flyTo,
        fitBounds,
        flyToWithLayer,
        fitBoundsWithLayer,
        ensureLayerVisible
    }
}
