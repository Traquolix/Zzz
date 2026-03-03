import { useEffect, useRef, useCallback } from 'react'
import { useMap } from '../MapContext'
import { useFibers } from '@/hooks/useFibers'
import { useRealtime } from '@/hooks/useRealtime'
import { parseDetections } from '@/lib/parseMessage'
import { getFiberOffsetCoords } from '@/lib/geoUtils'
import { ChannelDotAccumulator } from '@/lib/channelDots'

const STATIC_SOURCE_ID = 'channel-dots-static-source'
const STATIC_LAYER_ID = 'channel-dots-static-layer'
const ACTIVE_SOURCE_ID = 'channel-dots-active-source'
const ACTIVE_LAYER_ID = 'channel-dots-active-layer'

// Throttle: render at most every 200ms (5Hz) even if WebSocket arrives at 10Hz
const RENDER_THROTTLE_MS = 200

// Below this zoom level, dots are not visible — skip all GeoJSON work
const MIN_ZOOM = 13

/**
 * Speed -> green color (darker green at low speed, bright green at high speed).
 */
function speedToGreen(speed: number): string {
    const t = Math.min(1, Math.max(0, speed / 130))
    const r = Math.round(74 + t * (34 - 74))
    const g = Math.round(124 + t * (197 - 124))
    const b = Math.round(89 + t * (94 - 89))
    return `rgb(${r},${g},${b})`
}

/**
 * Speed -> dot radius. Bigger dots for faster detections.
 */
function speedToRadius(speed: number): number {
    const t = Math.min(1, Math.max(0, speed / 130))
    return 3 + t * 4
}

type ChannelEntry = {
    fiberLine: string
    channel: number
    direction: 0 | 1
    lng: number
    lat: number
}

/**
 * Build the static GeoJSON once — all channel positions with fixed styling.
 * No properties needed since the static layer uses fixed paint values.
 */
function buildStaticGeoJSON(channels: ChannelEntry[]): GeoJSON.FeatureCollection {
    const features: GeoJSON.Feature[] = channels.map(({ lng, lat }) => ({
        type: 'Feature',
        properties: {},
        geometry: { type: 'Point', coordinates: [lng, lat] },
    }))
    return { type: 'FeatureCollection', features }
}

/**
 * Detection dot layer — shows a dot at every channel position along all fibers.
 *
 * Uses a two-layer approach for performance:
 * - Static layer: all ~24,910 dots rendered once with fixed grey paint (no updates)
 * - Active layer: only active channels (~10-200) rebuilt every 200ms
 *
 * This reduces per-tick GeoJSON work by ~99%.
 */
export function ChannelDotLayer() {
    const map = useMap()
    const { fibers } = useFibers()
    const { subscribe } = useRealtime()

    const accRef = useRef(new ChannelDotAccumulator())
    const mountedRef = useRef(true)
    const dirtyRef = useRef(false)
    const lastRenderRef = useRef(0)
    const rafRef = useRef<number | null>(null)

    // Pre-build the base channel data (all channels, all fibers)
    const channelDataRef = useRef<{ allChannels: ChannelEntry[] } | null>(null)

    useEffect(() => {
        if (fibers.length === 0) {
            channelDataRef.current = null
            return
        }

        const allChannels: ChannelEntry[] = []

        for (const fiber of fibers) {
            const offsetCoords = getFiberOffsetCoords(fiber)
            const rawCoords = fiber.coordinates

            let offsetIdx = 0
            for (let ch = 0; ch < rawCoords.length; ch++) {
                const raw = rawCoords[ch]
                if (raw[0] != null && raw[1] != null) {
                    if (offsetIdx < offsetCoords.length) {
                        const [lng, lat] = offsetCoords[offsetIdx]
                        allChannels.push({
                            fiberLine: fiber.id,
                            channel: ch,
                            direction: fiber.direction,
                            lng,
                            lat,
                        })
                    }
                    offsetIdx++
                }
            }
        }

        channelDataRef.current = { allChannels }
    }, [fibers])

    // Build GeoJSON with only active channels (typically ~10-200 features)
    const buildActiveGeoJSON = useCallback((): GeoJSON.FeatureCollection => {
        const data = channelDataRef.current
        if (!data) return { type: 'FeatureCollection', features: [] }

        const acc = accRef.current
        const features: GeoJSON.Feature[] = []

        for (const { fiberLine, channel, direction, lng, lat } of data.allChannels) {
            const active = acc.getChannel(fiberLine, channel, direction)
            if (!active) continue

            features.push({
                type: 'Feature',
                properties: {
                    color: speedToGreen(active.speed),
                    radius: speedToRadius(active.speed),
                },
                geometry: { type: 'Point', coordinates: [lng, lat] },
            })
        }

        return { type: 'FeatureCollection', features }
    }, [])

    // Throttled render: push active GeoJSON to map at most every RENDER_THROTTLE_MS
    const flushToMap = useCallback(() => {
        if (!mountedRef.current || !dirtyRef.current) return

        const now = performance.now()
        const elapsed = now - lastRenderRef.current
        if (elapsed < RENDER_THROTTLE_MS) {
            if (rafRef.current === null) {
                rafRef.current = requestAnimationFrame(() => {
                    rafRef.current = null
                    flushToMap()
                })
            }
            return
        }

        dirtyRef.current = false
        lastRenderRef.current = now

        // Skip GeoJSON rebuild entirely when dots aren't visible
        if (map.getZoom() < MIN_ZOOM) return

        try {
            const source = map.getSource(ACTIVE_SOURCE_ID) as mapboxgl.GeoJSONSource
            if (source) source.setData(buildActiveGeoJSON())
        } catch {
            // Map may be destroyed
        }
    }, [map, buildActiveGeoJSON])

    // Subscribe to detections — update accumulator, mark dirty, throttle render
    useEffect(() => {
        return subscribe('detections', (data: unknown) => {
            const detections = parseDetections(data)
            accRef.current.setBatch(detections)
            dirtyRef.current = true
            flushToMap()
        })
    }, [subscribe, flushToMap])

    // Create sources/layers and render initial dots
    useEffect(() => {
        if (fibers.length === 0) return
        mountedRef.current = true

        const data = channelDataRef.current

        // --- Static layer: all dots, fixed grey paint, built once ---
        if (!map.getSource(STATIC_SOURCE_ID)) {
            map.addSource(STATIC_SOURCE_ID, {
                type: 'geojson',
                data: data
                    ? buildStaticGeoJSON(data.allChannels)
                    : { type: 'FeatureCollection', features: [] },
            })
        }

        if (!map.getLayer(STATIC_LAYER_ID)) {
            map.addLayer({
                id: STATIC_LAYER_ID,
                type: 'circle',
                source: STATIC_SOURCE_ID,
                minzoom: MIN_ZOOM,
                paint: {
                    'circle-radius': 3,
                    'circle-color': '#94a3b8',
                    'circle-opacity': 0.7,
                    'circle-stroke-width': 0.5,
                    'circle-stroke-color': '#94a3b8',
                    'circle-stroke-opacity': 0.3,
                },
            })
        }

        // --- Active layer: only active channels, data-driven paint, on top ---
        if (!map.getSource(ACTIVE_SOURCE_ID)) {
            map.addSource(ACTIVE_SOURCE_ID, {
                type: 'geojson',
                data: { type: 'FeatureCollection', features: [] },
            })
        }

        if (!map.getLayer(ACTIVE_LAYER_ID)) {
            map.addLayer({
                id: ACTIVE_LAYER_ID,
                type: 'circle',
                source: ACTIVE_SOURCE_ID,
                minzoom: MIN_ZOOM,
                paint: {
                    'circle-radius': ['get', 'radius'],
                    'circle-radius-transition': { duration: 300, delay: 0 },
                    'circle-color': ['get', 'color'],
                    'circle-color-transition': { duration: 200, delay: 0 },
                    'circle-opacity': 0.9,
                    'circle-stroke-width': 1.5,
                    'circle-stroke-color': '#ffffff',
                    'circle-stroke-opacity': 0.9,
                },
            })
        }

        // Initial render
        dirtyRef.current = true
        lastRenderRef.current = 0
        flushToMap()

        return () => {
            mountedRef.current = false
            if (rafRef.current !== null) {
                cancelAnimationFrame(rafRef.current)
                rafRef.current = null
            }
            try {
                if (map.getLayer(ACTIVE_LAYER_ID)) map.removeLayer(ACTIVE_LAYER_ID)
                if (map.getSource(ACTIVE_SOURCE_ID)) map.removeSource(ACTIVE_SOURCE_ID)
                if (map.getLayer(STATIC_LAYER_ID)) map.removeLayer(STATIC_LAYER_ID)
                if (map.getSource(STATIC_SOURCE_ID)) map.removeSource(STATIC_SOURCE_ID)
            } catch {
                // Map already destroyed
            }
        }
    }, [map, fibers, buildActiveGeoJSON, flushToMap])

    return null
}
