import { useEffect, useRef, useState } from 'react'
import { useMap } from '../MapContext'
import { useFibers } from '@/hooks/useFibers'
import { useSection } from '@/hooks/useSection'
import { filterValidCoords } from '@/lib/geoUtils'

// Orange to visually distinguish from snapped directional fiber lines
const CABLE_COLOR = '#f97316'

/**
 * Renders the parent fiber cables as center lines (no directional offset).
 * This shows the physical cable location, with directional fibers rendered
 * separately by FiberLayer as offset lines on either side.
 */
export function CableLayer() {
    const map = useMap()
    const { fibers, loading } = useFibers()
    const { layerVisibility } = useSection()
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

        map.on('style.load', checkAndSet)
        map.on('load', checkAndSet)
        map.on('idle', checkAndSet)
        checkAndSet()

        const timer = setTimeout(checkAndSet, 100)

        return () => {
            map.off('style.load', checkAndSet)
            map.off('load', checkAndSet)
            map.off('idle', checkAndSet)
            clearTimeout(timer)
        }
    }, [map, styleLoaded])

    // Add cable layers when style is loaded and fibers are available
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

        cleanup()

        // Don't render if layer is hidden
        if (!layerVisibility.cables) {
            return cleanup
        }

        const sourceIds: string[] = []
        const layerIds: string[] = []

        // Group fibers by parent to avoid rendering duplicate center lines
        const parentFiberIds = new Set<string>()
        const parentFiberCoords = new Map<string, [number, number][]>()

        for (const fiber of fibers) {
            const parentId = fiber.parentFiberId
            if (parentFiberIds.has(parentId)) continue
            parentFiberIds.add(parentId)

            // Use the original base coordinates (no directional offset) for the center line
            const rawCoords = fiber.baseCoordinates ?? fiber.coordinates
            const coords = filterValidCoords(rawCoords as ([number, number] | [null, null])[])
            if (coords.length >= 2) {
                parentFiberCoords.set(parentId, coords)
            }
        }

        // Render each parent fiber as a center line
        for (const [parentId, coords] of parentFiberCoords) {
            const sourceId = `cable-${parentId}`
            const layerId = `cable-layer-${parentId}`

            sourceIds.push(sourceId)
            layerIds.push(layerId)

            // Clean up stale sources
            try {
                if (map.getLayer(layerId)) map.removeLayer(layerId)
                if (map.getSource(sourceId)) map.removeSource(sourceId)
            } catch { /* style destroyed */ }

            // Add the center line
            map.addSource(sourceId, {
                type: 'geojson',
                data: {
                    type: 'Feature',
                    properties: { parentFiberId: parentId },
                    geometry: { type: 'LineString', coordinates: coords }
                }
            })

            map.addLayer({
                id: layerId,
                type: 'line',
                source: sourceId,
                layout: { 'line-join': 'round', 'line-cap': 'round' },
                paint: {
                    'line-color': CABLE_COLOR,
                    'line-width': 2,
                    'line-opacity': 0.7,
                }
            })
        }

        addedRef.current = { sourceIds, layerIds }

        return cleanup
    }, [map, fibers, loading, styleLoaded, layerVisibility.cables])

    return null
}
