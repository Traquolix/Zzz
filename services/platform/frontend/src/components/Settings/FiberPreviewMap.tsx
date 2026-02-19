import { useEffect, useRef } from 'react'
import mapboxgl from 'mapbox-gl'
import 'mapbox-gl/dist/mapbox-gl.css'
import type { FiberLine } from '@/types/fiber'
import type { SpeedLimitZone } from '@/types/speedLimit'
import { MAPBOX_TOKEN } from '@/config/mapbox'

mapboxgl.accessToken = MAPBOX_TOKEN

type Props = {
    fiber: FiberLine
    zones: SpeedLimitZone[]
}

export function FiberPreviewMap({ fiber, zones }: Props) {
    const containerRef = useRef<HTMLDivElement>(null)
    const mapRef = useRef<mapboxgl.Map | null>(null)

    // Initialize map
    useEffect(() => {
        if (!containerRef.current || mapRef.current) return

        const map = new mapboxgl.Map({
            container: containerRef.current,
            style: 'mapbox://styles/mapbox/light-v11',
            center: fiber.coordinates[Math.floor(fiber.coordinates.length / 2)],
            zoom: 12,
            attributionControl: false,
            interactive: false // Static preview
        })

        mapRef.current = map

        map.once('style.load', () => {
            // Fit to fiber bounds
            const bounds = new mapboxgl.LngLatBounds(fiber.coordinates[0], fiber.coordinates[0])
            for (const coord of fiber.coordinates) {
                bounds.extend(coord)
            }
            map.fitBounds(bounds, { padding: 20, duration: 0 })

            // Add layers
            updateLayers(map, fiber, zones)
        })

        return () => {
            if (mapRef.current) {
                mapRef.current.remove()
                mapRef.current = null
            }
        }
    }, [])

    // Update layers when fiber or zones change
    useEffect(() => {
        const map = mapRef.current
        if (!map || !map.isStyleLoaded()) return

        // Fit bounds to new fiber
        const bounds = new mapboxgl.LngLatBounds(fiber.coordinates[0], fiber.coordinates[0])
        for (const coord of fiber.coordinates) {
            bounds.extend(coord)
        }
        map.fitBounds(bounds, { padding: 20, duration: 500 })

        updateLayers(map, fiber, zones)
    }, [fiber, zones])

    return <div ref={containerRef} className="w-full h-full" />
}

function updateLayers(map: mapboxgl.Map, fiber: FiberLine, zones: SpeedLimitZone[]) {
    // Remove existing layers and sources
    const layerIds = ['fiber-preview-base', 'fiber-preview-zones']
    const sourceIds = ['fiber-preview-base-source', 'fiber-preview-zones-source']

    for (const id of layerIds) {
        if (map.getLayer(id)) map.removeLayer(id)
    }
    for (const id of sourceIds) {
        if (map.getSource(id)) map.removeSource(id)
    }

    // Base fiber line (gray, for uncovered areas)
    map.addSource('fiber-preview-base-source', {
        type: 'geojson',
        data: {
            type: 'Feature',
            properties: {},
            geometry: {
                type: 'LineString',
                coordinates: fiber.coordinates
            }
        }
    })

    map.addLayer({
        id: 'fiber-preview-base',
        type: 'line',
        source: 'fiber-preview-base-source',
        paint: {
            'line-color': '#cbd5e1', // slate-300
            'line-width': 4
        }
    })

    // Zone segments (colored)
    const zoneFeatures: GeoJSON.Feature[] = zones.map(zone => {
        const coords = fiber.coordinates.slice(zone.startChannel, zone.endChannel + 1)
        return {
            type: 'Feature' as const,
            properties: {
                limit: zone.limit,
                color: getLimitColor(zone.limit)
            },
            geometry: {
                type: 'LineString' as const,
                coordinates: coords
            }
        }
    }).filter(f => (f.geometry as GeoJSON.LineString).coordinates.length >= 2)

    map.addSource('fiber-preview-zones-source', {
        type: 'geojson',
        data: {
            type: 'FeatureCollection',
            features: zoneFeatures
        }
    })

    map.addLayer({
        id: 'fiber-preview-zones',
        type: 'line',
        source: 'fiber-preview-zones-source',
        paint: {
            'line-color': ['get', 'color'],
            'line-width': 6
        }
    })
}

function getLimitColor(limit: number): string {
    if (limit >= 100) return '#3b82f6' // blue - highway
    if (limit >= 70) return '#8b5cf6'  // purple - fast road
    if (limit >= 50) return '#f59e0b'  // amber - urban
    return '#ef4444'                    // red - slow zone
}
