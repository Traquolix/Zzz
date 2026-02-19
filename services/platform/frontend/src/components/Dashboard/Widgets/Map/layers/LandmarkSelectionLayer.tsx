import { useEffect, useRef, useCallback, useMemo } from 'react'
import mapboxgl from 'mapbox-gl'
import {useMap} from '../MapContext'
import {useFibers} from '@/hooks/useFibers'
import {useLandmarkSelection} from "@/hooks/useLandmarkSelection"
import {useSection} from "@/hooks/useSection"
import {getFiberOffsetCoords} from '@/lib/geoUtils'

/**
 * Handles landmark selection on map click.
 * Shows marker at selected landmark.
 * Optionally shows labels for named landmarks.
 */
export function LandmarkSelectionLayer() {
    const map = useMap()
    const { fibers } = useFibers()
    const {
        selectedLandmark,
        selectLandmark,
        landmarks: landmarkEntries,
        renameLandmark
    } = useLandmarkSelection()
    // Create a Map<string, string> for backward compatibility (key -> name)
    const landmarkNames = useMemo(() => {
        const names = new Map<string, string>()
        landmarkEntries.forEach((entry, key) => names.set(key, entry.name))
        return names
    }, [landmarkEntries])
    const { layerVisibility } = useSection()
    const showLabels = layerVisibility.landmarks

    // Precompute offset coordinates per fiber (or use precomputed if available)
    const fiberOffsetMap = useMemo(() => {
        const m = new Map<string, [number, number][]>()
        for (const fiber of fibers) {
            m.set(fiber.id, getFiberOffsetCoords(fiber))
        }
        return m
    }, [fibers])

    // Track which label is in "confirm delete" mode
    const pendingDeleteRef = useRef<{ key: string; el: HTMLDivElement; name: string; fiberId: string; channel: number } | null>(null)

    // Clear pending delete and restore label
    const clearPendingDelete = useCallback(() => {
        if (pendingDeleteRef.current) {
            const { el, name } = pendingDeleteRef.current
            el.textContent = name
            el.className = 'inline-block w-auto bg-blue-500 text-white px-2 py-1 rounded text-xs font-semibold shadow-md whitespace-nowrap cursor-pointer hover:bg-blue-600 transition-colors'
            pendingDeleteRef.current = null
        }
    }, [])

    // Set up global click listener to clear pending delete
    useEffect(() => {
        const handleGlobalClick = () => clearPendingDelete()
        document.addEventListener('click', handleGlobalClick)
        return () => document.removeEventListener('click', handleGlobalClick)
    }, [clearPendingDelete])

    const markerRef = useRef<mapboxgl.Marker | null>(null)
    const popupRef = useRef<mapboxgl.Popup | null>(null)

    // Show/update marker at selected landmark
    useEffect(() => {
        if (!map) return

        // Remove old marker
        if (markerRef.current) {
            markerRef.current.remove()
            markerRef.current = null
        }
        if (popupRef.current) {
            popupRef.current.remove()
            popupRef.current = null
        }

        if (!selectedLandmark) return

        // Get offset coordinates for the selected landmark (snap to directional fiber)
        const offsetCoords = fiberOffsetMap.get(selectedLandmark.fiberId)
        const coord = offsetCoords?.[selectedLandmark.channel]
        if (!coord || coord[0] == null || coord[1] == null) return

        // Create marker element
        // Note: Mapbox markers require DOM manipulation; Tailwind classes applied via className
        const el = document.createElement('div')
        el.className = 'w-5 h-5 bg-blue-500 border-[3px] border-white rounded-full shadow-lg cursor-pointer'

        markerRef.current = new mapboxgl.Marker({element: el})
            .setLngLat([coord[0], coord[1]])
            .addTo(map)

        return () => {
            if (markerRef.current) {
                markerRef.current.remove()
                markerRef.current = null
            }
        }
    }, [map, selectedLandmark, fiberOffsetMap])

    const labelMarkersRef = useRef<Map<string, mapboxgl.Marker>>(new Map())

    // Labels layer for named landmarks
    useEffect(() => {
        if (!map) return

        const currentKeys = new Set<string>()

        if (showLabels) {
            for (const [key, name] of landmarkNames) {
                currentKeys.add(key)

                if (labelMarkersRef.current.has(key)) continue

                // Key format: "fiberId:channel" — but fiberId itself contains ":" (e.g. "carros:0")
                const lastColon = key.lastIndexOf(':')
                const fiberId = key.slice(0, lastColon)
                const channel = parseInt(key.slice(lastColon + 1), 10)
                const offsetCoords = fiberOffsetMap.get(fiberId)
                if (!offsetCoords || !offsetCoords[channel]) continue
                const coord = offsetCoords[channel]
                if (coord[0] == null || coord[1] == null) continue

                const [lng, lat] = coord

                const el = document.createElement('div')
                el.className = 'inline-block w-auto bg-blue-500 text-white px-2 py-1 rounded text-xs font-semibold shadow-md whitespace-nowrap cursor-pointer hover:bg-blue-600 transition-colors'
                el.textContent = name

                // Confirm deletion (used by both click and right-click)
                const confirmDelete = () => {
                    if (pendingDeleteRef.current?.key === key) {
                        renameLandmark(fiberId, channel, '') // Delete the label
                        selectLandmark(null) // Deselect the landmark
                        pendingDeleteRef.current = null
                        return true
                    }
                    return false
                }

                // Enter delete confirmation mode
                const enterDeleteMode = () => {
                    // Clear any existing pending delete on another label
                    clearPendingDelete()

                    pendingDeleteRef.current = { key, el, name, fiberId, channel }
                    el.textContent = 'Delete?'
                    el.className = 'inline-block w-auto bg-red-500 text-white px-2 py-1 rounded text-xs font-semibold shadow-md whitespace-nowrap cursor-pointer hover:bg-red-600 transition-colors'
                }

                // Click handler - either confirm delete or select landmark
                el.addEventListener('click', (e) => {
                    e.stopPropagation()

                    // If this label is pending delete, confirm it
                    if (confirmDelete()) return

                    // Clear any other pending delete
                    clearPendingDelete()

                    // Select the landmark
                    selectLandmark({
                        fiberId,
                        channel,
                        lat,
                        lng
                    })
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

                const marker = new mapboxgl.Marker({ element: el, anchor: 'bottom', offset: [0, -10] })
                    .setLngLat([lng, lat])
                    .addTo(map)

                labelMarkersRef.current.set(key, marker)
            }
        }

        // Remove old markers
        for (const [key, marker] of labelMarkersRef.current) {
            if (!currentKeys.has(key) || !showLabels) {
                marker.remove()
                labelMarkersRef.current.delete(key)
            }
        }

        return () => {
            // Cleanup handled by removal logic above
        }
    }, [map, fibers, fiberOffsetMap, landmarkNames, showLabels, renameLandmark, selectLandmark, clearPendingDelete])

    // Cleanup on unmount
    useEffect(() => {
        const markers = labelMarkersRef.current

        return () => {
            if (!map) return

            try {
                const sourceId = 'landmark-labels-source'
                const layerId = 'landmark-labels-layer'
                if (map.getLayer(layerId)) map.removeLayer(layerId)
                if (map.getSource(sourceId)) map.removeSource(sourceId)
            } catch {
                // Map style already destroyed
            }

            for (const marker of markers.values()) {
                marker.remove()
            }
            markers.clear()
        }
    }, [map])

    return null
}
