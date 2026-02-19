import { useEffect, useRef, useCallback } from 'react'
import mapboxgl from 'mapbox-gl'
import { useMap } from '../MapContext'
import { useFibers } from '@/hooks/useFibers'
import { useSection } from '@/hooks/useSection'
import { filterValidCoords, getFiberOffsetCoords } from '@/lib/geoUtils'

const HIGHLIGHT_SOURCE_ID = 'section-highlight-source'
const HIGHLIGHT_LAYER_ID = 'section-highlight-layer'
const SELECTED_SOURCE_ID = 'section-selected-source'
const SELECTED_LAYER_ID = 'section-selected-layer'
const PREVIEW_SOURCE_ID = 'section-preview-source'
const PREVIEW_LAYER_ID = 'section-preview-layer'

export function SectionLayer() {
    const map = useMap()
    const { fibers } = useFibers()
    const {
        sections,
        selectedSection,
        selectSection,
        deleteSection,
        hoveredSectionId,
        setHoveredSectionId,
        pendingPoint,
        layerVisibility,
        setPreviewChannel
    } = useSection()

    const labelMarkersRef = useRef<Map<string, mapboxgl.Marker>>(new Map())
    const labelDataRef = useRef<Map<string, string>>(new Map()) // Track name+bounds hash to detect changes

    // Track which label is in "confirm delete" mode
    const pendingDeleteRef = useRef<{ sectionId: string; el: HTMLDivElement; name: string } | null>(null)

    // Clear pending delete and restore label
    const clearPendingDelete = useCallback(() => {
        if (pendingDeleteRef.current) {
            const { el, name } = pendingDeleteRef.current
            el.textContent = name
            el.className = 'inline-block w-auto bg-green-600 text-white px-2 py-1 rounded text-xs font-semibold shadow-md whitespace-nowrap cursor-pointer hover:bg-green-700 transition-colors'
            pendingDeleteRef.current = null
        }
    }, [])

    // Set up global click listener to clear pending delete
    useEffect(() => {
        const handleGlobalClick = () => clearPendingDelete()
        document.addEventListener('click', handleGlobalClick)
        return () => document.removeEventListener('click', handleGlobalClick)
    }, [clearPendingDelete])

    // Render preview line from pending point to cursor during section creation
    useEffect(() => {
        if (!map || !pendingPoint) {
            // Remove preview if no pending point
            setPreviewChannel(null)
            try {
                if (map?.getLayer(PREVIEW_LAYER_ID)) map.removeLayer(PREVIEW_LAYER_ID)
                if (map?.getSource(PREVIEW_SOURCE_ID)) map.removeSource(PREVIEW_SOURCE_ID)
            } catch { /* ignore */ }
            return
        }

        const fiber = fibers.find(f => f.id === pendingPoint.fiberId)
        if (!fiber) return

        const fiberOffset = getFiberOffsetCoords(fiber)

        // Get coordinates from pendingPoint to cursor position
        const handleMouseMove = (e: mapboxgl.MapMouseEvent) => {
            const { lng, lat } = e.lngLat

            // Find nearest channel on the fiber's offset line (skip null coords)
            let nearestChannel = pendingPoint.channel
            let minDist = Infinity
            for (let ch = 0; ch < fiberOffset.length; ch++) {
                const coord = fiberOffset[ch]
                if (coord[0] == null || coord[1] == null) continue
                const d = Math.hypot(coord[0] - lng, coord[1] - lat)
                if (d < minDist) {
                    minDist = d
                    nearestChannel = ch
                }
            }

            // Update preview channel for UI feedback
            setPreviewChannel(nearestChannel)

            const startCh = Math.min(pendingPoint.channel, nearestChannel)
            const endCh = Math.max(pendingPoint.channel, nearestChannel)
            const previewCoords = filterValidCoords(fiberOffset.slice(startCh, endCh + 1))

            if (previewCoords.length < 2) return

            try {
                if (map.getSource(PREVIEW_SOURCE_ID)) {
                    (map.getSource(PREVIEW_SOURCE_ID) as mapboxgl.GeoJSONSource).setData({
                        type: 'Feature',
                        properties: {},
                        geometry: {
                            type: 'LineString',
                            coordinates: previewCoords
                        }
                    })
                } else {
                    map.addSource(PREVIEW_SOURCE_ID, {
                        type: 'geojson',
                        data: {
                            type: 'Feature',
                            properties: {},
                            geometry: {
                                type: 'LineString',
                                coordinates: previewCoords
                            }
                        }
                    })
                    map.addLayer({
                        id: PREVIEW_LAYER_ID,
                        type: 'line',
                        source: PREVIEW_SOURCE_ID,
                        layout: {
                            'line-join': 'round',
                            'line-cap': 'round'
                        },
                        paint: {
                            'line-color': '#3b82f6', // blue
                            'line-width': 8,
                            'line-opacity': 0.5,
                            'line-dasharray': [2, 2]
                        }
                    })
                }
            } catch { /* ignore */ }
        }

        map.on('mousemove', handleMouseMove)

        return () => {
            map.off('mousemove', handleMouseMove)
            setPreviewChannel(null)
            try {
                if (map.getLayer(PREVIEW_LAYER_ID)) map.removeLayer(PREVIEW_LAYER_ID)
                if (map.getSource(PREVIEW_SOURCE_ID)) map.removeSource(PREVIEW_SOURCE_ID)
            } catch { /* ignore */ }
        }
    }, [map, pendingPoint, fibers, setPreviewChannel])

    // Render section highlight when hovered
    useEffect(() => {
        if (!map) return

        // Remove existing highlight
        try {
            if (map.getLayer(HIGHLIGHT_LAYER_ID)) map.removeLayer(HIGHLIGHT_LAYER_ID)
            if (map.getSource(HIGHLIGHT_SOURCE_ID)) map.removeSource(HIGHLIGHT_SOURCE_ID)
        } catch {
            // Source/layer doesn't exist, that's fine
        }

        if (!hoveredSectionId) return

        const section = sections.get(hoveredSectionId)
        if (!section) return

        const fiber = fibers.find(f => f.id === section.fiberId)
        if (!fiber) return

        // Extract coordinates for the section on the offset line
        const fiberOffset = getFiberOffsetCoords(fiber)
        const sectionCoords = filterValidCoords(fiberOffset.slice(section.startChannel, section.endChannel + 1))
        if (sectionCoords.length < 2) return

        map.addSource(HIGHLIGHT_SOURCE_ID, {
            type: 'geojson',
            data: {
                type: 'Feature',
                properties: {},
                geometry: {
                    type: 'LineString',
                    coordinates: sectionCoords
                }
            }
        })

        map.addLayer({
            id: HIGHLIGHT_LAYER_ID,
            type: 'line',
            source: HIGHLIGHT_SOURCE_ID,
            layout: {
                'line-join': 'round',
                'line-cap': 'round'
            },
            paint: {
                'line-color': '#f59e0b', // amber
                'line-width': 10,
                'line-opacity': 0.7
            }
        })

        return () => {
            try {
                if (map.getLayer(HIGHLIGHT_LAYER_ID)) map.removeLayer(HIGHLIGHT_LAYER_ID)
                if (map.getSource(HIGHLIGHT_SOURCE_ID)) map.removeSource(HIGHLIGHT_SOURCE_ID)
            } catch {
                // Map destroyed
            }
        }
    }, [map, hoveredSectionId, sections, fibers])

    // Render selected section highlight (persistent, different color)
    useEffect(() => {
        if (!map) return

        // Remove existing selection highlight
        try {
            if (map.getLayer(SELECTED_LAYER_ID)) map.removeLayer(SELECTED_LAYER_ID)
            if (map.getSource(SELECTED_SOURCE_ID)) map.removeSource(SELECTED_SOURCE_ID)
        } catch { /* ignore */ }

        if (!selectedSection) return

        const section = sections.get(selectedSection.sectionId)
        if (!section) return

        const fiber = fibers.find(f => f.id === section.fiberId)
        if (!fiber) return

        const fiberOffset = getFiberOffsetCoords(fiber)
        const sectionCoords = filterValidCoords(fiberOffset.slice(section.startChannel, section.endChannel + 1))
        if (sectionCoords.length < 2) return

        map.addSource(SELECTED_SOURCE_ID, {
            type: 'geojson',
            data: {
                type: 'Feature',
                properties: {},
                geometry: {
                    type: 'LineString',
                    coordinates: sectionCoords
                }
            }
        })

        map.addLayer({
            id: SELECTED_LAYER_ID,
            type: 'line',
            source: SELECTED_SOURCE_ID,
            layout: {
                'line-join': 'round',
                'line-cap': 'round'
            },
            paint: {
                'line-color': '#22c55e', // green
                'line-width': 8,
                'line-opacity': 0.8
            }
        })

        return () => {
            try {
                if (map.getLayer(SELECTED_LAYER_ID)) map.removeLayer(SELECTED_LAYER_ID)
                if (map.getSource(SELECTED_SOURCE_ID)) map.removeSource(SELECTED_SOURCE_ID)
            } catch { /* ignore */ }
        }
    }, [map, selectedSection, sections, fibers])

    // Render section labels
    useEffect(() => {
        if (!map) return

        const currentKeys = new Set<string>()

        if (layerVisibility.sections) {
            for (const [sectionId, section] of sections) {
                currentKeys.add(sectionId)

                // Create hash of section data to detect changes
                const dataHash = `${section.name}|${section.startChannel}|${section.endChannel}`
                const existingHash = labelDataRef.current.get(sectionId)

                // If marker exists but data changed, remove it so we recreate
                if (labelMarkersRef.current.has(sectionId) && existingHash !== dataHash) {
                    labelMarkersRef.current.get(sectionId)?.remove()
                    labelMarkersRef.current.delete(sectionId)
                    labelDataRef.current.delete(sectionId)
                }

                if (labelMarkersRef.current.has(sectionId)) continue

                const fiber = fibers.find(f => f.id === section.fiberId)
                if (!fiber) continue

                const fiberOffset = getFiberOffsetCoords(fiber)

                // Calculate midpoint channel — find nearest valid coordinate to midpoint
                const midChannel = Math.floor((section.startChannel + section.endChannel) / 2)
                let coords = fiberOffset[midChannel]
                // If midpoint has null GPS, search outward for a valid coordinate
                if (!coords || coords[0] == null || coords[1] == null) {
                    let found = false
                    for (let ofs = 1; ofs <= (section.endChannel - section.startChannel); ofs++) {
                        for (const ch of [midChannel + ofs, midChannel - ofs]) {
                            if (ch >= section.startChannel && ch <= section.endChannel) {
                                const c = fiberOffset[ch]
                                if (c && c[0] != null && c[1] != null) {
                                    coords = c
                                    found = true
                                    break
                                }
                            }
                        }
                        if (found) break
                    }
                    if (!found) continue
                }

                const [lng, lat] = coords

                const el = document.createElement('div')
                el.className = 'inline-block w-auto bg-green-600 text-white px-2 py-1 rounded text-xs font-semibold shadow-md whitespace-nowrap cursor-pointer hover:bg-green-700 transition-colors'
                el.textContent = section.name

                // Confirm deletion (used by both click and right-click)
                const confirmDelete = () => {
                    if (pendingDeleteRef.current?.sectionId === sectionId) {
                        deleteSection(sectionId)
                        pendingDeleteRef.current = null
                        return true
                    }
                    return false
                }

                // Enter delete confirmation mode
                const enterDeleteMode = () => {
                    // Clear any existing pending delete on another label
                    clearPendingDelete()

                    pendingDeleteRef.current = { sectionId, el, name: section.name }
                    el.textContent = 'Delete?'
                    el.className = 'inline-block w-auto bg-red-500 text-white px-2 py-1 rounded text-xs font-semibold shadow-md whitespace-nowrap cursor-pointer hover:bg-red-600 transition-colors'
                }

                // Click handler - either confirm delete or select section
                el.addEventListener('click', (e) => {
                    e.stopPropagation()

                    // If this label is pending delete, confirm it
                    if (confirmDelete()) return

                    // Clear any other pending delete
                    clearPendingDelete()

                    // Select the section
                    selectSection({ sectionId, fiberId: section.fiberId })
                })

                // Right-click - enter delete mode OR confirm if already in delete mode
                el.addEventListener('contextmenu', (e) => {
                    e.preventDefault()
                    e.stopPropagation()

                    // If already in delete mode, confirm
                    if (confirmDelete()) return

                    // Enter delete confirmation mode
                    enterDeleteMode()
                })

                // Hover handlers for highlighting
                el.addEventListener('mouseenter', () => {
                    setHoveredSectionId(sectionId)
                })
                el.addEventListener('mouseleave', () => {
                    setHoveredSectionId(null)
                })

                const marker = new mapboxgl.Marker({ element: el, anchor: 'bottom', offset: [0, -10] })
                    .setLngLat([lng, lat])
                    .addTo(map)

                labelMarkersRef.current.set(sectionId, marker)
                labelDataRef.current.set(sectionId, dataHash)
            }
        }

        // Remove old markers
        for (const [key, marker] of labelMarkersRef.current) {
            if (!currentKeys.has(key) || !layerVisibility.sections) {
                marker.remove()
                labelMarkersRef.current.delete(key)
                labelDataRef.current.delete(key)
            }
        }
    }, [map, fibers, sections, layerVisibility.sections, setHoveredSectionId, selectSection, deleteSection, clearPendingDelete])

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
                if (map?.getLayer(PREVIEW_LAYER_ID)) map.removeLayer(PREVIEW_LAYER_ID)
                if (map?.getSource(PREVIEW_SOURCE_ID)) map.removeSource(PREVIEW_SOURCE_ID)
            } catch {
                // Map destroyed
            }
        }
    }, [map])

    return null
}
