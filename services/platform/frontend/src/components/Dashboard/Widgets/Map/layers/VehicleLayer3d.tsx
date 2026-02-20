import { useEffect, useRef } from 'react'
import { SimpleMeshLayer } from '@deck.gl/mesh-layers'
import { CubeGeometry } from '@luma.gl/engine'
import { useDeckOverlay, useMap } from '../MapContext'
import { useFibers } from '@/hooks/useFibers'
import { useRealtime } from '@/hooks/useRealtime'
import { useSpeedLimits } from '@/hooks/useSpeedLimits'
import { VehicleSimEngine } from '@/lib/vehicleSim'
import { getSpeedLimitForChannel, speedToRGBWithLimit } from '@/types/speedLimit'
import { parseDetections } from '@/lib/parseMessage'
import type { VehiclePosition } from '@/types/selection'
import { useVehicleSelection } from '@/hooks/useVehicleSelection'
import { useSection } from '@/hooks/useSection'
import { getFiberOffsetCoords } from '@/lib/geoUtils'

type FiberEngine = {
    engine: VehicleSimEngine
    coordinates: [number, number][]
    offsetCoords: [number, number][]
    fiberId: string
    direction: 0 | 1
}

// Performance: throttle deck.gl updates to 30fps
const DECK_UPDATE_INTERVAL_MS = 33
// Throttle React state updates (vehicle positions) to 10fps
const POSITION_UPDATE_INTERVAL_MS = 100
// Zoom threshold: below this, show heatmap; at/above this, show individual cars
const ZOOM_THRESHOLD = 14
// Fade transition range around threshold
const ZOOM_FADE_LOW = ZOOM_THRESHOLD - 0.5  // Start fading in at 13.5
const ZOOM_FADE_HIGH = ZOOM_THRESHOLD + 0.5 // Fully visible at 14.5

// Pre-allocated accessor functions (avoid creating new closures every frame)
const getVehiclePosition = (d: VehiclePosition) => d.position
const getVehicleOrientation = (d: VehiclePosition): [number, number, number] => [0, -d.angle, 0]
const getVehicleScale = (d: VehiclePosition): [number, number, number] => {
    if (d.isRawDetection) return [1.5, 1.5, 3]
    if (d.isDetectionMarker) return [2, 4, 1.5]
    return [3, 6, 2]
}

// Placeholder accessors for the empty warm-up layer
const emptyPosition = () => [0, 0, 0] as [number, number, number]
const emptyColor = () => [0, 0, 0, 0] as [number, number, number, number]
const emptyOrientation = () => [0, 0, 0] as [number, number, number]
const emptyScale = () => [1, 1, 1] as [number, number, number]

export function VehicleLayer3D() {
    const deckOverlay = useDeckOverlay()
    const map = useMap()
    const { fibers } = useFibers()
    const { subscribe } = useRealtime()
    const { zones } = useSpeedLimits()
    const { selectedVehicle, selectVehicle, setVehiclePositions } = useVehicleSelection()
    const { layerVisibility } = useSection()

    const enginesRef = useRef<Map<string, FiberEngine>>(new Map())
    const lastFrameRef = useRef<number>(0)
    const lastDeckUpdateRef = useRef<number>(0)
    const lastPositionUpdateRef = useRef<number>(0)
    const cubeRef = useRef<CubeGeometry | null>(null)
    const rafIdRef = useRef<number | null>(null)
    const selectedIdRef = useRef<string | null>(null)
    const showDetectionsRef = useRef(layerVisibility.detections)
    const zoomRef = useRef(map.getZoom())
    const zonesRef = useRef(zones)
    // Keep ref updated for use in render loop
    useEffect(() => { zonesRef.current = zones }, [zones])

    // Track zoom level (ref only, no state)
    useEffect(() => {
        const onZoom = () => {
            zoomRef.current = map.getZoom()
        }
        map.on('zoom', onZoom)
        return () => { map.off('zoom', onZoom) }
    }, [map])

    useEffect(() => { showDetectionsRef.current = layerVisibility.detections }, [layerVisibility.detections])
    useEffect(() => { selectedIdRef.current = selectedVehicle?.id ?? null }, [selectedVehicle?.id])
    useEffect(() => { if (!cubeRef.current) cubeRef.current = new CubeGeometry() }, [])

    useEffect(() => {
        if (fibers.length === 0) return
        const engines = enginesRef.current

        for (const fiber of fibers) {
            if (!engines.has(fiber.id)) {
                // Use precomputed coordinates if available, otherwise compute offset
                const offsetCoords = getFiberOffsetCoords(fiber)

                engines.set(fiber.id, {
                    engine: new VehicleSimEngine({
                        totalChannels: fiber.coordinates.length,
                        metersPerChannel: 5,
                        fadeOutAfterMs: 3000,
                        fadeDurationMs: 1500,
                        maxLanes: 10,
                        segmentWidth: 0.8,
                        confirmationCount: 2,
                        maxCoastingMs: 5000,
                        gateThreshold: 3.0,
                        minGateChannels: 20
                    }),
                    coordinates: fiber.coordinates,
                    offsetCoords,
                    fiberId: fiber.id,
                    direction: fiber.direction
                })
            }
        }

        for (const [id] of engines) {
            if (!fibers.find(f => f.id === id)) engines.delete(id)
        }
    }, [fibers])

    useEffect(() => {
        let loggedOnce = false
        return subscribe('detections', (data: unknown) => {
            const detections = parseDetections(data)
            if (detections.length === 0) return

            // Debug: log first batch to verify matching
            if (!loggedOnce) {
                const engineKeys = Array.from(enginesRef.current.keys())
                const sampleDetection = detections[0]
                const sampleDirectionalId = `${sampleDetection.fiberLine}:${sampleDetection.direction}`
                console.log('[VehicleLayer3d] First detection batch:', {
                    detectionsCount: detections.length,
                    sampleFiberLine: sampleDetection.fiberLine,
                    sampleDirection: sampleDetection.direction,
                    constructedId: sampleDirectionalId,
                    engineKeys: engineKeys.slice(0, 6),
                    willMatch: enginesRef.current.has(sampleDirectionalId)
                })
                loggedOnce = true
            }

            const now = performance.now()
            let matched = 0, unmatched = 0
            for (const d of detections) {
                // Construct directional fiber ID: parent:direction (e.g., "mathis:0")
                const directionalId = `${d.fiberLine}:${d.direction}`
                const fe = enginesRef.current.get(directionalId)
                if (fe) {
                    matched++
                    fe.engine.onSensorEvent({
                        channel: d.channel,
                        speed: d.speed,
                        count: d.count,
                        direction: d.direction
                    }, now)
                } else {
                    unmatched++
                }
            }

            // Warn if detections aren't matching (throttled)
            if (unmatched > 0 && Math.random() < 0.01) {
                console.warn(`[VehicleLayer3d] ${unmatched}/${detections.length} detections unmatched`)
            }
        })
    }, [subscribe])

    useEffect(() => {
        if (!deckOverlay || !cubeRef.current || !map) return

        let cancelled = false
        const cube = cubeRef.current

        const tick = () => {
            if (cancelled) return

            const now = performance.now()
            const deltaMs = lastFrameRef.current === 0 ? 16 : now - lastFrameRef.current
            lastFrameRef.current = now

            // Always tick engines at 60fps for smooth physics
            for (const [, { engine }] of enginesRef.current) {
                engine.tick(now, deltaMs)
            }

            // Throttle deck.gl updates to ~30fps
            const timeSinceLastDeckUpdate = now - lastDeckUpdateRef.current
            if (timeSinceLastDeckUpdate < DECK_UPDATE_INTERVAL_MS) {
                rafIdRef.current = requestAnimationFrame(tick)
                return
            }
            lastDeckUpdateRef.current = now

            // Calculate zoom-based opacity for smooth transition
            const zoom = zoomRef.current
            const zoomOpacity = zoom < ZOOM_FADE_LOW
                ? 0
                : zoom > ZOOM_FADE_HIGH
                    ? 1
                    : (zoom - ZOOM_FADE_LOW) / (ZOOM_FADE_HIGH - ZOOM_FADE_LOW)

            // At very low zoom, render a minimal layer to keep shaders/GPU resources warm
            // This avoids the shader recompilation lag when crossing the zoom threshold
            const skipFullRender = zoomOpacity === 0

            // Get viewport bounds for culling
            const bounds = map.getBounds()
            if (!bounds) {
                rafIdRef.current = requestAnimationFrame(tick)
                return
            }
            const minLng = bounds.getWest()
            const maxLng = bounds.getEast()
            const minLat = bounds.getSouth()
            const maxLat = bounds.getNorth()
            const lngMargin = (maxLng - minLng) * 0.1
            const latMargin = (maxLat - minLat) * 0.1

            const positions: VehiclePosition[] = []

            // Skip position calculations when zoomed out, but still render empty layer
            if (skipFullRender) {
                setVehiclePositions([])
                // Create layer with empty data to keep GPU resources warm
                const layer = new SimpleMeshLayer({
                    id: 'vehicle-3d-layer',
                    data: [],
                    mesh: cube,
                    getPosition: emptyPosition,
                    getColor: emptyColor,
                    getOrientation: emptyOrientation,
                    getScale: emptyScale,
                    sizeScale: 1,
                    pickable: false,
                    autoHighlight: false
                })
                try {
                    deckOverlay.setProps({ layers: [layer] })
                } catch {
                    // Viewport not ready
                }
                rafIdRef.current = requestAnimationFrame(tick)
                return
            }

            for (const [, { engine, coordinates, offsetCoords, fiberId, direction }] of enginesRef.current) {
                // Render vehicles (Kalman-estimated positions)
                for (const track of engine.tracks) {
                    const renderChannel = engine.getTrackPosition(track)
                    const renderSpeed = engine.getRenderSpeed(track)
                    const detectionSpeed = engine.getDetectionSpeed(track)

                    for (const car of track.cars) {
                        if (car.opacity <= 0) continue

                        const ch = renderChannel + car.offset * 10
                        const pos = channelToCoord(ch, offsetCoords)
                        if (!pos) continue

                        // Viewport culling
                        if (pos.lng < minLng - lngMargin || pos.lng > maxLng + lngMargin ||
                            pos.lat < minLat - latMargin || pos.lat > maxLat + latMargin) {
                            continue
                        }

                        positions.push({
                            id: `${track.id}:${car.id}`,
                            fiberId,
                            position: [pos.lng, pos.lat, 0],
                            angle: getBearing(ch, coordinates, direction),
                            speed: renderSpeed,
                            detectionSpeed: detectionSpeed,
                            channel: ch,
                            direction,
                            isDetectionMarker: false,
                            opacity: car.opacity * track.opacity,
                            trackState: track.state
                        })
                    }

                    // Show last detection position as marker (if enabled)
                    if (showDetectionsRef.current) {
                        const pos = channelToCoord(track.lastDetectionChannel, offsetCoords)
                        if (pos &&
                            pos.lng >= minLng - lngMargin && pos.lng <= maxLng + lngMargin &&
                            pos.lat >= minLat - latMargin && pos.lat <= maxLat + latMargin) {
                            positions.push({
                                id: `detection-${track.id}`,
                                fiberId,
                                position: [pos.lng, pos.lat, 0],
                                angle: getBearing(track.lastDetectionChannel, coordinates, direction),
                                speed: detectionSpeed,
                                detectionSpeed: detectionSpeed,
                                channel: track.lastDetectionChannel,
                                direction,
                                isDetectionMarker: true,
                                opacity: 0.7,
                                innovation: track.lastInnovation
                            })
                        }
                    }
                }

                // Also show recent raw detections as fading markers
                if (showDetectionsRef.current) {
                    for (const det of engine.recentDetections) {
                        const age = now - det.timestamp
                        const opacity = Math.max(0, 1 - age / 500)
                        if (opacity <= 0) continue

                        const pos = channelToCoord(det.channel, offsetCoords)
                        if (!pos) continue

                        // Viewport culling
                        if (pos.lng < minLng - lngMargin || pos.lng > maxLng + lngMargin ||
                            pos.lat < minLat - latMargin || pos.lat > maxLat + latMargin) {
                            continue
                        }

                        positions.push({
                            id: `raw-${det.timestamp}-${det.channel}`,
                            fiberId,
                            position: [pos.lng, pos.lat, 0.5],
                            angle: getBearing(det.channel, coordinates, direction),
                            speed: det.speed,
                            detectionSpeed: det.speed,
                            channel: det.channel,
                            direction,
                            isDetectionMarker: true,
                            isRawDetection: true,
                            opacity: opacity * 0.8
                        })
                    }
                }
            }

            // Throttle setVehiclePositions to avoid excessive React re-renders
            const timeSincePositionUpdate = now - lastPositionUpdateRef.current
            if (timeSincePositionUpdate >= POSITION_UPDATE_INTERVAL_MS) {
                lastPositionUpdateRef.current = now
                setVehiclePositions(positions)
            }

            // Update selected vehicle tooltip at full frame rate for smooth following
            if (selectedIdRef.current) {
                const v = positions.find(p => p.id === selectedIdRef.current && !p.isDetectionMarker)
                if (v) {
                    const pt = map.project([v.position[0], v.position[1]])
                    selectVehicle({
                        id: v.id,
                        speed: v.speed,
                        detectionSpeed: v.detectionSpeed,
                        channel: v.channel,
                        direction: v.direction,
                        screenX: pt.x,
                        screenY: pt.y
                    })
                } else {
                    selectVehicle(null)
                }
            }

            if (cancelled) return

            const layer = new SimpleMeshLayer({
                id: 'vehicle-3d-layer',
                data: positions,
                mesh: cube,
                getPosition: getVehiclePosition,
                getColor: (d: VehiclePosition) => {
                    if (d.isRawDetection) {
                        return [255, 100, 50, Math.floor((d.opacity ?? 1) * zoomOpacity * 255)]
                    }
                    if (d.isDetectionMarker) {
                        return [100, 150, 255, Math.floor((d.opacity ?? 1) * zoomOpacity * 180)]
                    }
                    const speedLimit = getSpeedLimitForChannel(d.fiberId, d.channel, zonesRef.current)
                    const [r, g, b] = speedToRGBWithLimit(d.speed, speedLimit)
                    const alpha = Math.floor((d.opacity ?? 1) * zoomOpacity * 220)
                    return [r, g, b, alpha]
                },
                getOrientation: getVehicleOrientation,
                getScale: getVehicleScale,
                sizeScale: 1,
                pickable: false,
                autoHighlight: false
            })

            try {
                deckOverlay.setProps({ layers: [layer] })
            } catch {
                // Viewport not ready or destroyed - this is expected during editing mode transitions
            }

            if (!cancelled) {
                rafIdRef.current = requestAnimationFrame(tick)
            }
        }

        if (map.loaded()) {
            rafIdRef.current = requestAnimationFrame(tick)
        } else {
            map.once('idle', () => {
                if (!cancelled) rafIdRef.current = requestAnimationFrame(tick)
            })
        }

        return () => {
            cancelled = true
            if (rafIdRef.current) {
                cancelAnimationFrame(rafIdRef.current)
                rafIdRef.current = null
            }
            try {
                deckOverlay.setProps({ layers: [] })
            } catch {
                // Already destroyed
            }
        }
    }, [deckOverlay, map, setVehiclePositions, selectVehicle])

    return null
}

function channelToCoord(channel: number, coords: [number, number][]): { lng: number; lat: number } | null {
    if (coords.length < 2) return null
    const c = Math.max(0, Math.min(coords.length - 1, channel))
    const i = Math.floor(c)
    const j = Math.min(i + 1, coords.length - 1)
    const t = c - i
    return { lng: coords[i][0] + (coords[j][0] - coords[i][0]) * t, lat: coords[i][1] + (coords[j][1] - coords[i][1]) * t }
}

function getBearing(channel: number, coords: [number, number][], direction: 0 | 1): number {
    if (coords.length < 2) return 0
    const i = Math.max(0, Math.min(coords.length - 2, Math.floor(channel)))
    const [lng1, lat1] = coords[i]
    const [lng2, lat2] = coords[i + 1]
    const dLng = (lng2 - lng1) * Math.PI / 180
    const lat1R = lat1 * Math.PI / 180
    const lat2R = lat2 * Math.PI / 180
    const y = Math.sin(dLng) * Math.cos(lat2R)
    const x = Math.cos(lat1R) * Math.sin(lat2R) - Math.sin(lat1R) * Math.cos(lat2R) * Math.cos(dLng)
    const b = (Math.atan2(y, x) * 180 / Math.PI + 360) % 360
    return direction === 0 ? b : (b + 180) % 360
}

