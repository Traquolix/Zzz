import { useEffect, useRef } from 'react'
import mapboxgl from 'mapbox-gl'
import { useMap } from '../MapContext'
import { useFibers } from '@/hooks/useFibers'
import { useInfrastructure } from '@/hooks/useInfrastructure'
import { useSection } from '@/hooks/useSection'
import { logger } from '@/lib/logger'

const HIGHLIGHT_SOURCE_ID = 'infrastructure-highlight-source'
const HIGHLIGHT_LAYER_ID = 'infrastructure-highlight-layer'
const SELECTED_SOURCE_ID = 'infrastructure-selected-source'
const SELECTED_LAYER_ID = 'infrastructure-selected-layer'

// Colors for infrastructure types
const TYPE_COLORS: Record<string, string> = {
    bridge: '#f59e0b', // amber
    tunnel: '#6366f1'  // indigo
}

export function InfrastructureLayer() {
    const map = useMap()
    const { fibers } = useFibers()
    const { infrastructures, selectedInfrastructure, selectInfrastructure } = useInfrastructure()
    const { layerVisibility } = useSection()

    const labelMarkersRef = useRef<Map<string, mapboxgl.Marker>>(new Map())
    const hoveredIdRef = useRef<string | null>(null)

    // Render infrastructure labels (similar to section labels)
    useEffect(() => {
        if (!map) return

        const currentKeys = new Set<string>()

        if (layerVisibility.infrastructure) {
            for (const infra of infrastructures) {
                currentKeys.add(infra.id)

                if (labelMarkersRef.current.has(infra.id)) continue

                // Infrastructure stores parent fiber ID (e.g., "carros"), match against parentFiberId
                const fiber = fibers.find(f => f.parentFiberId === infra.fiberId)
                if (!fiber) continue

                // Calculate midpoint channel
                const midChannel = Math.floor((infra.startChannel + infra.endChannel) / 2)
                const coords = fiber.coordinates[midChannel]
                if (!coords) continue

                const [lng, lat] = coords
                const color = TYPE_COLORS[infra.type] || '#6b7280'

                const el = document.createElement('div')
                el.className = `inline-flex items-center gap-1 text-white px-2 py-1 rounded text-xs font-semibold shadow-md whitespace-nowrap cursor-pointer transition-colors`
                el.style.backgroundColor = color

                // Create SVG icon
                const icon = document.createElementNS('http://www.w3.org/2000/svg', 'svg')
                icon.setAttribute('class', 'w-3 h-3')
                icon.setAttribute('fill', 'none')
                icon.setAttribute('viewBox', '0 0 24 24')
                icon.setAttribute('stroke-width', '2')
                icon.setAttribute('stroke', 'currentColor')
                const path = document.createElementNS('http://www.w3.org/2000/svg', 'path')
                path.setAttribute('stroke-linecap', 'round')
                path.setAttribute('stroke-linejoin', 'round')
                path.setAttribute('d', 'M2.25 21h19.5m-18-18v18m10.5-18v18m6-13.5V21M6.75 6.75h.75m-.75 3h.75m-.75 3h.75m3-6h.75m-.75 3h.75m-.75 3h.75M6.75 21v-3.375c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125V21M3 3h12m-.75 4.5H21m-3.75 3H21m-3.75 3H21')
                icon.appendChild(path)
                el.appendChild(icon)

                const text = document.createElement('span')
                text.textContent = infra.name
                el.appendChild(text)

                // Click to select
                el.addEventListener('click', (e) => {
                    e.stopPropagation()
                    selectInfrastructure({
                        id: infra.id,
                        name: infra.name,
                        type: infra.type,
                        fiberId: infra.fiberId,
                        startChannel: infra.startChannel,
                        endChannel: infra.endChannel
                    })
                })

                // Hover handlers for highlighting
                el.addEventListener('mouseenter', () => {
                    hoveredIdRef.current = infra.id
                    el.style.transform = 'scale(1.05)'
                    updateHighlight()
                })
                el.addEventListener('mouseleave', () => {
                    hoveredIdRef.current = null
                    el.style.transform = 'scale(1)'
                    updateHighlight()
                })

                const marker = new mapboxgl.Marker({ element: el, anchor: 'bottom', offset: [0, -10] })
                    .setLngLat([lng, lat])
                    .addTo(map)

                labelMarkersRef.current.set(infra.id, marker)
            }
        }

        // Remove old markers
        for (const [key, marker] of labelMarkersRef.current) {
            if (!currentKeys.has(key) || !layerVisibility.infrastructure) {
                marker.remove()
                labelMarkersRef.current.delete(key)
            }
        }
    }, [map, fibers, infrastructures, layerVisibility.infrastructure, selectInfrastructure])

    // Update hovered highlight
    const updateHighlight = () => {
        if (!map) return

        // Remove existing highlight
        try {
            if (map.getLayer(HIGHLIGHT_LAYER_ID)) map.removeLayer(HIGHLIGHT_LAYER_ID)
            if (map.getSource(HIGHLIGHT_SOURCE_ID)) map.removeSource(HIGHLIGHT_SOURCE_ID)
        } catch (error) {
            logger.debug('Map cleanup (highlight):', error)
        }

        const hoveredId = hoveredIdRef.current
        if (!hoveredId) return

        const infra = infrastructures.find(i => i.id === hoveredId)
        if (!infra) return

        const fiber = fibers.find(f => f.parentFiberId === infra.fiberId)
        if (!fiber) return

        const coords = fiber.coordinates.slice(infra.startChannel, infra.endChannel + 1)
        if (coords.length < 2) return

        try {
            map.addSource(HIGHLIGHT_SOURCE_ID, {
                type: 'geojson',
                data: {
                    type: 'Feature',
                    properties: {},
                    geometry: { type: 'LineString', coordinates: coords }
                }
            })

            map.addLayer({
                id: HIGHLIGHT_LAYER_ID,
                type: 'line',
                source: HIGHLIGHT_SOURCE_ID,
                layout: { 'line-join': 'round', 'line-cap': 'round' },
                paint: {
                    'line-color': TYPE_COLORS[infra.type] || '#6b7280',
                    'line-width': 10,
                    'line-opacity': 0.5
                }
            })
        } catch (error) {
            logger.debug('Map cleanup (add highlight):', error)
        }
    }

    // Render selected infrastructure highlight
    useEffect(() => {
        if (!map) return

        // Remove existing selection highlight
        try {
            if (map.getLayer(SELECTED_LAYER_ID)) map.removeLayer(SELECTED_LAYER_ID)
            if (map.getSource(SELECTED_SOURCE_ID)) map.removeSource(SELECTED_SOURCE_ID)
        } catch (error) {
            logger.debug('Map cleanup (selected):', error)
        }

        if (!selectedInfrastructure) return

        const infra = infrastructures.find(i => i.id === selectedInfrastructure.id)
        if (!infra) return

        const fiber = fibers.find(f => f.parentFiberId === infra.fiberId)
        if (!fiber) return

        const coords = fiber.coordinates.slice(infra.startChannel, infra.endChannel + 1)
        if (coords.length < 2) return

        try {
            map.addSource(SELECTED_SOURCE_ID, {
                type: 'geojson',
                data: {
                    type: 'Feature',
                    properties: {},
                    geometry: { type: 'LineString', coordinates: coords }
                }
            })

            map.addLayer({
                id: SELECTED_LAYER_ID,
                type: 'line',
                source: SELECTED_SOURCE_ID,
                layout: { 'line-join': 'round', 'line-cap': 'round' },
                paint: {
                    'line-color': TYPE_COLORS[infra.type] || '#6b7280',
                    'line-width': 8,
                    'line-opacity': 0.8
                }
            })
        } catch { /* ignore */ }

        return () => {
            try {
                if (map.getLayer(SELECTED_LAYER_ID)) map.removeLayer(SELECTED_LAYER_ID)
                if (map.getSource(SELECTED_SOURCE_ID)) map.removeSource(SELECTED_SOURCE_ID)
            } catch (error) {
                logger.debug('Map cleanup (selected unmount):', error)
            }
        }
    }, [map, selectedInfrastructure, infrastructures, fibers])

    // Cleanup on unmount
    useEffect(() => {
        const markers = labelMarkersRef.current

        return () => {
            for (const marker of markers.values()) {
                marker.remove()
            }
            markers.clear()

            try {
                if (map?.getLayer(HIGHLIGHT_LAYER_ID)) map.removeLayer(HIGHLIGHT_LAYER_ID)
                if (map?.getSource(HIGHLIGHT_SOURCE_ID)) map.removeSource(HIGHLIGHT_SOURCE_ID)
                if (map?.getLayer(SELECTED_LAYER_ID)) map.removeLayer(SELECTED_LAYER_ID)
                if (map?.getSource(SELECTED_SOURCE_ID)) map.removeSource(SELECTED_SOURCE_ID)
            } catch (error) {
                logger.debug('Map cleanup (full unmount):', error)
            }
        }
    }, [map])

    return null
}
