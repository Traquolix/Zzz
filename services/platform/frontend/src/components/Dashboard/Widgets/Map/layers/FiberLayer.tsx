import { useEffect, useRef, useState } from 'react'
import { useMap } from '../MapContext'
import { useFibers } from '@/hooks/useFibers'
import { getFiberOffsetCoords } from '@/lib/geoUtils'

// Light grey color for all fibers
const FIBER_COLOR = '#9ca3af'

/**
 * Renders each directional fiber as a single offset line.
 * Each fiber in the array already has a direction (0 or 1) — the backend
 * expands physical cables into two directional fibers.
 */
export function FiberLayer() {
    const map = useMap()
    const { fibers, loading } = useFibers()
    const addedRef = useRef<{ sourceIds: string[]; layerIds: string[] } | null>(null)
    const [styleLoaded, setStyleLoaded] = useState(map.isStyleLoaded())

    // Track when map style becomes loaded
    useEffect(() => {
        if (styleLoaded) return

        const checkAndSet = () => {
            if (map.isStyleLoaded()) {
                setStyleLoaded(true)
            }
        }

        // Listen for style.load, load, and idle events
        map.on('style.load', checkAndSet)
        map.on('load', checkAndSet)
        map.on('idle', checkAndSet)

        // Check immediately in case map is already loaded
        checkAndSet()

        // Also check after a short delay as a fallback
        const timer = setTimeout(checkAndSet, 100)

        return () => {
            map.off('style.load', checkAndSet)
            map.off('load', checkAndSet)
            map.off('idle', checkAndSet)
            clearTimeout(timer)
        }
    }, [map, styleLoaded])

    // Add fiber layers when both style is loaded AND fibers are available
    useEffect(() => {
        if (!styleLoaded || loading || fibers.length === 0) return

        function cleanup() {
            const added = addedRef.current
            if (!added) return
            try {
                for (const layerId of added.layerIds) {
                    if (map.getLayer(layerId)) map.removeLayer(layerId)
                }
                for (const sourceId of added.sourceIds) {
                    if (map.getSource(sourceId)) map.removeSource(sourceId)
                }
            } catch { /* Map style already destroyed */ }
            addedRef.current = null
        }

        // Clean up any existing layers first
        cleanup()

        const sourceIds: string[] = []
        const layerIds: string[] = []

        for (const fiber of fibers) {
            const sourceId = `fiber-${fiber.id}`
            const layerId = `fiber-layer-${fiber.id}`
            const hitSourceId = `fiber-${fiber.id}-hit`
            const hitLayerId = `fiber-layer-${fiber.id}-hit`

            sourceIds.push(sourceId, hitSourceId)
            layerIds.push(layerId, hitLayerId)

            // Clean up stale sources from prior render if they exist
            try {
                if (map.getLayer(layerId)) map.removeLayer(layerId)
                if (map.getLayer(hitLayerId)) map.removeLayer(hitLayerId)
                if (map.getSource(sourceId)) map.removeSource(sourceId)
                if (map.getSource(hitSourceId)) map.removeSource(hitSourceId)
            } catch { /* style destroyed */ }

            // Use precomputed coordinates if available, otherwise compute offset
            const coords = getFiberOffsetCoords(fiber)

            if (coords.length < 2) continue

            // Visible direction line
            map.addSource(sourceId, {
                type: 'geojson',
                data: {
                    type: 'Feature',
                    properties: { name: fiber.name, fiberId: fiber.id, direction: fiber.direction },
                    geometry: { type: 'LineString', coordinates: coords }
                }
            })
            map.addLayer({
                id: layerId,
                type: 'line',
                source: sourceId,
                layout: { 'line-join': 'round', 'line-cap': 'round' },
                paint: { 'line-color': FIBER_COLOR, 'line-width': 3, 'line-opacity': 0.8 }
            })

            // Invisible wider hit-area layer for easier click targeting
            map.addSource(hitSourceId, {
                type: 'geojson',
                data: {
                    type: 'Feature',
                    properties: { name: fiber.name, fiberId: fiber.id, direction: fiber.direction },
                    geometry: { type: 'LineString', coordinates: coords }
                }
            })
            map.addLayer({
                id: hitLayerId,
                type: 'line',
                source: hitSourceId,
                layout: { 'line-join': 'round', 'line-cap': 'round' },
                paint: { 'line-color': FIBER_COLOR, 'line-width': 8, 'line-opacity': 0 }
            })
        }

        addedRef.current = { sourceIds, layerIds }

        return cleanup
    }, [map, fibers, loading, styleLoaded])

    return null
}
