import { useEffect, useRef } from 'react'
import { useMap } from '../MapContext'
import { useFibers } from '@/hooks/useFibers'
import { useRealtime } from '@/hooks/useRealtime'
import { useSpeedLimits } from '@/hooks/useSpeedLimits'
import { getSpeedLimitForChannel, speedToColorWithLimit } from '@/types/speedLimit'
import { parseDetections } from '@/lib/parseMessage'
import { getFiberOffsetCoords } from '@/lib/geoUtils'

const ZOOM_THRESHOLD = 14
const SPEED_DECAY_MS = 10000 // speed data expires after 10s
const UPDATE_INTERVAL_MS = 1000 // Update heatmap every second

type SegmentSpeed = {
    totalSpeed: number
    count: number
    lastUpdate: number
}

// Key: "segmentIndex:direction" (e.g. "5:0", "5:1")
type FiberSegments = Map<string, SegmentSpeed>

/**
 * Shows fiber lines colored by average speed at low zoom levels.
 * At high zoom, this layer is hidden and individual vehicles are shown instead.
 *
 * Performance: Uses refs instead of state to avoid React re-renders during map interactions.
 */
export function SpeedHeatmapLayer() {
    const map = useMap()
    const { fibers } = useFibers()
    const { subscribe } = useRealtime()
    const { zones } = useSpeedLimits()

    const speedDataRef = useRef<Map<string, FiberSegments>>(new Map())
    const zonesRef = useRef(zones)
    // Keep ref updated for use in non-reactive callbacks
    useEffect(() => {
        zonesRef.current = zones
    }, [zones])
    const layerIdsRef = useRef<string[]>([])
    const sourceIdsRef = useRef<string[]>([])
    const layersCreatedRef = useRef(false)
    const intervalRef = useRef<number | null>(null)
    const mountedRef = useRef(true)

    // Subscribe to detections and aggregate speeds (no state updates here)
    useEffect(() => {
        return subscribe('detections', (data: unknown) => {
            const detections = parseDetections(data)
            if (detections.length === 0) return

            const now = Date.now()
            const speedData = speedDataRef.current

            for (const d of detections) {
                // fiberLine is now directional from backend (e.g., "mathis:0")
                let fiberData = speedData.get(d.fiberLine)
                if (!fiberData) {
                    fiberData = new Map()
                    speedData.set(d.fiberLine, fiberData)
                }

                // Adaptive segmentation: ~50m segments (10 channels at 5m each)
                const segmentIdx = Math.floor(d.channel / 10)
                const key = `${segmentIdx}:${d.direction}`
                const existing = fiberData.get(key)

                if (existing && now - existing.lastUpdate < 3000) {
                    // Exponential moving average for smoother transitions
                    const alpha = 0.3
                    existing.totalSpeed = existing.totalSpeed * (1 - alpha) + d.speed * d.count * alpha
                    existing.count = Math.max(1, existing.count * (1 - alpha) + d.count * alpha)
                    existing.lastUpdate = now
                } else {
                    fiberData.set(key, {
                        totalSpeed: d.speed * d.count,
                        count: d.count,
                        lastUpdate: now
                    })
                }
            }
        })
    }, [subscribe])

    // Setup layers once on mount, toggle visibility via opacity based on zoom
    useEffect(() => {
        if (fibers.length === 0) return
        mountedRef.current = true

        const updateLayerData = () => {
            const now = Date.now()
            const speedData = speedDataRef.current

            for (const fiber of fibers) {
                // Use precomputed coordinates if available, otherwise compute offset
                const dirCoords = getFiberOffsetCoords(fiber)

                // Each fiber in the list is already directional (e.g., carros:0, carros:1)
                // so we only need one layer per fiber, not two
                const sourceId = `speed-heatmap-${fiber.id}-dir${fiber.direction}`
                const source = map.getSource(sourceId) as mapboxgl.GeoJSONSource
                if (!source) continue

                const fiberSpeeds = speedData.get(fiber.id)
                const features = buildSegmentFeatures(fiber.id, dirCoords, fiberSpeeds, now, zonesRef.current, fiber.direction)

                source.setData({
                    type: 'FeatureCollection',
                    features
                })
            }
        }

        const createLayers = () => {
            if (layersCreatedRef.current) return

            for (const fiber of fibers) {
                // Each fiber in the list is already directional (e.g., carros:0, carros:1)
                const sourceId = `speed-heatmap-${fiber.id}-dir${fiber.direction}`
                const layerId = `speed-heatmap-layer-${fiber.id}-dir${fiber.direction}`

                if (map.getSource(sourceId)) continue

                // Find the fiber layer to insert before
                const fiberLayerId = `fiber-layer-${fiber.id}`
                const beforeLayer = map.getLayer(fiberLayerId) ? fiberLayerId : undefined

                map.addSource(sourceId, {
                    type: 'geojson',
                    data: { type: 'FeatureCollection', features: [] }
                })

                map.addLayer({
                    id: layerId,
                    type: 'line',
                    source: sourceId,
                    layout: {
                        'line-join': 'round',
                        'line-cap': 'round'
                    },
                    paint: {
                        'line-color': ['get', 'color'],
                        'line-width': 4,
                        'line-opacity': 0 // Start hidden, controlled by zoom
                    }
                }, beforeLayer)

                if (!sourceIdsRef.current.includes(sourceId)) {
                    sourceIdsRef.current.push(sourceId)
                }
                if (!layerIdsRef.current.includes(layerId)) {
                    layerIdsRef.current.push(layerId)
                }
            }

            layersCreatedRef.current = true

            // Start update interval for data (always running)
            if (!intervalRef.current) {
                intervalRef.current = window.setInterval(updateLayerData, UPDATE_INTERVAL_MS)
                updateLayerData() // Initial update
            }
        }

        const cleanup = () => {
            if (intervalRef.current) {
                clearInterval(intervalRef.current)
                intervalRef.current = null
            }
            map.off('zoom', updateOpacity)
            try {
                for (const layerId of layerIdsRef.current) {
                    if (map.getLayer(layerId)) map.removeLayer(layerId)
                }
                for (const sourceId of sourceIdsRef.current) {
                    if (map.getSource(sourceId)) map.removeSource(sourceId)
                }
            } catch {
                // Map already destroyed
            }
            layerIdsRef.current = []
            sourceIdsRef.current = []
            layersCreatedRef.current = false
        }

        // Update opacity based on zoom level - checked frequently for smooth transitions
        const updateOpacity = () => {
            // Guard against component unmount / map being destroyed
            if (!mountedRef.current) return
            try {
                if (!map.getContainer()) return
            } catch {
                return
            }

            const zoom = map.getZoom()
            // Fade from full opacity at zoom 13.5 to 0 at zoom 14.5
            const opacity = zoom < ZOOM_THRESHOLD - 0.5
                ? 0.85
                : zoom > ZOOM_THRESHOLD + 0.5
                    ? 0
                    : 0.85 * (1 - (zoom - (ZOOM_THRESHOLD - 0.5)))

            for (const layerId of layerIdsRef.current) {
                try {
                    if (map.getLayer(layerId)) {
                        map.setPaintProperty(layerId, 'line-opacity', opacity)
                    }
                } catch {
                    // Layer might be removed
                }
            }
        }

        // Create layers immediately
        createLayers()

        // Listen to zoom changes for smooth opacity transitions
        map.on('zoom', updateOpacity)
        updateOpacity() // Initial check

        return () => {
            mountedRef.current = false
            cleanup()
        }
    }, [map, fibers])

    return null
}

function buildSegmentFeatures(
    fiberId: string,
    coordinates: [number, number][],
    fiberSpeeds: FiberSegments | undefined,
    now: number,
    zones: Map<string, import('@/types/speedLimit').SpeedLimitZone>,
    direction: 0 | 1
): GeoJSON.Feature[] {
    if (!fiberSpeeds || fiberSpeeds.size === 0) {
        return []
    }

    const features: GeoJSON.Feature[] = []
    const segmentSize = 10 // 10 channels per segment (~50m at 5m/channel)
    const numSegments = Math.ceil(coordinates.length / segmentSize)

    for (let i = 0; i < numSegments; i++) {
        const startIdx = i * segmentSize
        const endIdx = Math.min((i + 1) * segmentSize, coordinates.length - 1)

        if (startIdx >= coordinates.length - 1) continue

        const segmentCoords = coordinates.slice(startIdx, endIdx + 1)
        if (segmentCoords.length < 2) continue

        const key = `${i}:${direction}`
        const speedInfo = fiberSpeeds.get(key)
        if (!speedInfo || now - speedInfo.lastUpdate >= SPEED_DECAY_MS) {
            continue // No recent data - skip this segment
        }

        const avgSpeed = speedInfo.totalSpeed / speedInfo.count
        // Use midpoint of segment for speed limit lookup
        const midChannel = startIdx + Math.floor((endIdx - startIdx) / 2)
        const speedLimit = getSpeedLimitForChannel(fiberId, midChannel, zones)
        const color = speedToColorWithLimit(avgSpeed, speedLimit)

        features.push({
            type: 'Feature',
            properties: { color, segmentIndex: i, direction },
            geometry: {
                type: 'LineString',
                coordinates: segmentCoords
            }
        })
    }

    return features
}
