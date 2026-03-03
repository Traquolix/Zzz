import { useEffect, useRef, useCallback } from 'react'
import mapboxgl from 'mapbox-gl'
import { MAPBOX_TOKEN } from '@/config/mapbox'
import { fibers, vehicles, incidents, severityColor, incidentTypeIcon, MAP_CENTER, MAP_ZOOM, SAMPLING_STEP } from '../data'
import type { Section, PendingPoint } from '../types'

interface PrototypeMapProps {
    onIncidentClick?: (id: string) => void
    sectionCreationMode?: boolean
    pendingPoint?: PendingPoint | null
    sections?: Section[]
    onFiberClick?: (point: PendingPoint) => void
    onSectionComplete?: (fiberId: string, startChannel: number, endChannel: number) => void
    onCancelCreation?: () => void
}

// Find nearest point on any fiber to a given [lng, lat], within a distance threshold
function findNearestFiberPoint(lngLat: [number, number], maxDistDeg = 0.003) {
    let best: { fiberId: string; index: number; dist: number } | null = null

    for (const fiber of fibers) {
        // Only check direction 0 to avoid duplicate clicks on the same cable
        if (fiber.direction !== 0) continue
        for (let i = 0; i < fiber.coordinates.length; i++) {
            const [lng, lat] = fiber.coordinates[i]
            const dx = lng - lngLat[0]
            const dy = lat - lngLat[1]
            const dist = Math.sqrt(dx * dx + dy * dy)
            if (dist < maxDistDeg && (!best || dist < best.dist)) {
                best = { fiberId: fiber.id, index: i, dist }
            }
        }
    }

    if (!best) return null

    const fiber = fibers.find((f) => f.id === best!.fiberId)!
    const coord = fiber.coordinates[best.index]
    const step = SAMPLING_STEP[fiber.parentCableId] ?? 1
    const channel = best.index * step

    return { fiberId: best.fiberId, channel, lng: coord[0], lat: coord[1] }
}

export function PrototypeMap({
    onIncidentClick,
    sectionCreationMode,
    pendingPoint,
    sections,
    onFiberClick,
    onSectionComplete,
}: PrototypeMapProps) {
    const containerRef = useRef<HTMLDivElement>(null)
    const mapRef = useRef<mapboxgl.Map | null>(null)
    const markersRef = useRef<mapboxgl.Marker[]>([])
    // Stable callback ref to avoid re-creating the map when handlers change
    const handlersRef = useRef({ onIncidentClick, onFiberClick, onSectionComplete })
    handlersRef.current = { onIncidentClick, onFiberClick, onSectionComplete }

    const pendingPointRef = useRef(pendingPoint)
    pendingPointRef.current = pendingPoint

    const sectionCreationRef = useRef(sectionCreationMode)
    sectionCreationRef.current = sectionCreationMode

    // Initialize map once
    useEffect(() => {
        if (!containerRef.current || mapRef.current) return

        mapboxgl.accessToken = MAPBOX_TOKEN

        const map = new mapboxgl.Map({
            container: containerRef.current,
            style: 'mapbox://styles/mapbox/dark-v11',
            center: MAP_CENTER,
            zoom: MAP_ZOOM,
            pitch: 30,
            antialias: true,
        })

        mapRef.current = map

        map.on('load', () => {
            // ── Fiber route layers ──────────────────────────────────
            const seenCables = new Set<string>()

            fibers.forEach((fiber) => {
                map.addSource(`fiber-${fiber.id}`, {
                    type: 'geojson',
                    data: {
                        type: 'Feature',
                        properties: { name: fiber.name },
                        geometry: { type: 'LineString', coordinates: fiber.coordinates },
                    },
                })

                map.addLayer({
                    id: `fiber-line-${fiber.id}`,
                    type: 'line',
                    source: `fiber-${fiber.id}`,
                    paint: {
                        'line-color': fiber.color,
                        'line-width': 2.5,
                        'line-opacity': 0.8,
                    },
                })

                // Cable name label (once per cable)
                if (!seenCables.has(fiber.parentCableId)) {
                    seenCables.add(fiber.parentCableId)
                    const mid = fiber.coordinates[Math.floor(fiber.coordinates.length / 2)]
                    const el = document.createElement('div')
                    el.textContent = fiber.name
                    el.style.cssText = `
                        font-size: 10px; color: #e2e8f0; padding: 1px 5px;
                        background: rgba(43,45,49,0.8); border-radius: 3px;
                        pointer-events: none; white-space: nowrap;
                    `
                    const marker = new mapboxgl.Marker({ element: el, anchor: 'left' })
                        .setLngLat(mid)
                        .setOffset([6, 0])
                        .addTo(map)
                    markersRef.current.push(marker)
                }
            })

            // ── Vehicle dots (speed-colored) ────────────────────────
            const vehicleFeatures = vehicles.map((v) => ({
                type: 'Feature' as const,
                properties: { id: v.id, speed: v.speed },
                geometry: { type: 'Point' as const, coordinates: v.position },
            }))

            map.addSource('vehicles', {
                type: 'geojson',
                data: { type: 'FeatureCollection', features: vehicleFeatures },
            })

            map.addLayer({
                id: 'vehicle-dots',
                type: 'circle',
                source: 'vehicles',
                paint: {
                    'circle-radius': 4,
                    'circle-color': [
                        'step', ['get', 'speed'],
                        '#ef4444',
                        30, '#f97316',
                        60, '#eab308',
                        80, '#22c55e',
                    ],
                    'circle-opacity': 0.8,
                    'circle-stroke-color': 'rgba(0,0,0,0.3)',
                    'circle-stroke-width': 1,
                },
            })

            // ── Incident markers (DOM-based with icons) ─────────────
            incidents.forEach((inc) => {
                if (inc.resolved) return

                const el = document.createElement('div')
                el.style.cssText = `
                    width: 22px; height: 22px; border-radius: 5px;
                    background-color: ${severityColor[inc.severity]};
                    border: 2px solid rgba(255,255,255,0.7);
                    display: flex; align-items: center; justify-content: center;
                    font-size: 11px; color: white; cursor: pointer;
                    font-weight: bold; line-height: 1;
                `
                el.textContent = incidentTypeIcon[inc.type] ?? '!'
                el.title = inc.title

                el.addEventListener('click', () => {
                    handlersRef.current.onIncidentClick?.(inc.id)
                })

                const marker = new mapboxgl.Marker({ element: el })
                    .setLngLat(inc.location)
                    .addTo(map)
                markersRef.current.push(marker)
            })

            // ── Section highlight source (empty, updated via effect) ─
            map.addSource('section-highlights', {
                type: 'geojson',
                data: { type: 'FeatureCollection', features: [] },
            })

            map.addLayer({
                id: 'section-highlight-layer',
                type: 'line',
                source: 'section-highlights',
                paint: {
                    'line-color': ['get', 'color'],
                    'line-width': 6,
                    'line-opacity': 0.35,
                },
            })

            // ── Pending section preview source ──────────────────────
            map.addSource('pending-section', {
                type: 'geojson',
                data: { type: 'FeatureCollection', features: [] },
            })

            map.addLayer({
                id: 'pending-section-layer',
                type: 'line',
                source: 'pending-section',
                paint: {
                    'line-color': '#f59e0b',
                    'line-width': 4,
                    'line-opacity': 0.6,
                    'line-dasharray': [2, 2],
                },
            })

            // ── Pending point marker source ─────────────────────────
            map.addSource('pending-point', {
                type: 'geojson',
                data: { type: 'FeatureCollection', features: [] },
            })

            map.addLayer({
                id: 'pending-point-layer',
                type: 'circle',
                source: 'pending-point',
                paint: {
                    'circle-radius': 6,
                    'circle-color': '#f59e0b',
                    'circle-stroke-color': '#fff',
                    'circle-stroke-width': 2,
                },
            })

            // ── Map click handler for section creation ──────────────
            map.on('click', (e) => {
                if (!sectionCreationRef.current) return

                const hit = findNearestFiberPoint([e.lngLat.lng, e.lngLat.lat])
                if (!hit) return

                const pending = pendingPointRef.current
                if (!pending) {
                    handlersRef.current.onFiberClick?.(hit)
                } else {
                    // Must be same cable
                    const hitCable = hit.fiberId.split(':')[0]
                    const pendingCable = pending.fiberId.split(':')[0]
                    if (hitCable !== pendingCable) return

                    const start = Math.min(pending.channel, hit.channel)
                    const end = Math.max(pending.channel, hit.channel)
                    if (end - start < 10) return // too small

                    handlersRef.current.onSectionComplete?.(pending.fiberId, start, end)
                }
            })
        })

        // ── ResizeObserver ──────────────────────────────────────
        let resizeRafId: number | null = null
        const scheduleResize = () => {
            if (resizeRafId !== null) return
            resizeRafId = requestAnimationFrame(() => {
                resizeRafId = null
                map.resize()
            })
        }

        const resizer = new ResizeObserver(() => scheduleResize())
        resizer.observe(containerRef.current)

        return () => {
            resizer.disconnect()
            if (resizeRafId !== null) cancelAnimationFrame(resizeRafId)
            markersRef.current.forEach((m) => m.remove())
            markersRef.current = []
            map.remove()
            mapRef.current = null
        }
    }, [])

    // ── Update section highlights when sections change ───────────
    const updateSectionHighlights = useCallback((map: mapboxgl.Map, secs: Section[]) => {
        const source = map.getSource('section-highlights') as mapboxgl.GeoJSONSource | undefined
        if (!source) return

        const features = secs.map((sec) => {
            const fiber = fibers.find((f) => f.id === sec.fiberId)
            if (!fiber) return null
            const step = SAMPLING_STEP[fiber.parentCableId] ?? 1
            const startIdx = Math.max(0, Math.floor(sec.startChannel / step))
            const endIdx = Math.min(fiber.coordinates.length - 1, Math.ceil(sec.endChannel / step))
            const coords = fiber.coordinates.slice(startIdx, endIdx + 1)
            if (coords.length < 2) return null

            return {
                type: 'Feature' as const,
                properties: { color: fiber.color },
                geometry: { type: 'LineString' as const, coordinates: coords },
            }
        }).filter(Boolean)

        source.setData({ type: 'FeatureCollection', features: features as GeoJSON.Feature[] })
    }, [])

    useEffect(() => {
        const map = mapRef.current
        if (!map || !map.isStyleLoaded()) return
        updateSectionHighlights(map, sections ?? [])
    }, [sections, updateSectionHighlights])

    // ── Update pending point marker ─────────────────────────────
    useEffect(() => {
        const map = mapRef.current
        if (!map || !map.isStyleLoaded()) return

        const pointSource = map.getSource('pending-point') as mapboxgl.GeoJSONSource | undefined
        if (!pointSource) return

        if (pendingPoint) {
            pointSource.setData({
                type: 'FeatureCollection',
                features: [{
                    type: 'Feature',
                    properties: {},
                    geometry: { type: 'Point', coordinates: [pendingPoint.lng, pendingPoint.lat] },
                }],
            })
        } else {
            pointSource.setData({ type: 'FeatureCollection', features: [] })
        }

        // Clear pending section preview when no pending point
        const sectionSource = map.getSource('pending-section') as mapboxgl.GeoJSONSource | undefined
        if (sectionSource && !pendingPoint) {
            sectionSource.setData({ type: 'FeatureCollection', features: [] })
        }
    }, [pendingPoint])

    // ── Map cursor in creation mode ─────────────────────────────
    useEffect(() => {
        const map = mapRef.current
        if (!map) return
        map.getCanvas().style.cursor = sectionCreationMode ? 'crosshair' : ''
    }, [sectionCreationMode])

    return <div ref={containerRef} className="w-full h-full" />
}
