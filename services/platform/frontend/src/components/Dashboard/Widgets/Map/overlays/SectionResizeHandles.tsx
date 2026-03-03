import { useEffect, useRef, useCallback, useState, useMemo } from 'react'
import mapboxgl from 'mapbox-gl'
import { useMap } from '../MapContext'
import { useFibers } from '@/hooks/useFibers'
import { useSection } from '@/hooks/useSection'
import { getFiberOffsetCoords } from '@/lib/geoUtils'

export function SectionResizeHandles() {
    const map = useMap()
    const { fibers } = useFibers()
    const {
        sections,
        selectedSection,
        updateSectionBounds,
        draggingEndpoint,
        setDraggingEndpoint
    } = useSection()

    const startMarkerRef = useRef<mapboxgl.Marker | null>(null)
    const endMarkerRef = useRef<mapboxgl.Marker | null>(null)
    const [tempBounds, setTempBounds] = useState<{ start: number; end: number } | null>(null)
    const tempBoundsRef = useRef(tempBounds)
    tempBoundsRef.current = tempBounds

    const section = selectedSection ? sections.get(selectedSection.sectionId) : null
    const fiber = section ? fibers.find(f => f.id === section.fiberId) : null

    // Compute offset coordinates for the fiber (or use precomputed if available)
    const fiberOffsetCoords = useMemo(() => {
        if (!fiber) return null
        return getFiberOffsetCoords(fiber)
    }, [fiber])

    // Find nearest channel for a given coordinate on offset line
    const findNearestChannel = useCallback((lng: number, lat: number) => {
        if (!fiberOffsetCoords) return null
        let nearest = 0
        let minDist = Infinity
        for (let ch = 0; ch < fiberOffsetCoords.length; ch++) {
            const coord = fiberOffsetCoords[ch]
            if (coord[0] == null || coord[1] == null) continue
            const d = Math.hypot(coord[0] - lng, coord[1] - lat)
            if (d < minDist) {
                minDist = d
                nearest = ch
            }
        }
        return nearest
    }, [fiberOffsetCoords])

    // Create draggable handle element
    const createHandleElement = useCallback((type: 'start' | 'end') => {
        const el = document.createElement('div')
        el.className = 'w-6 h-6 md:w-4 md:h-4 bg-green-500 border-2 border-white rounded-full shadow-lg cursor-grab active:cursor-grabbing'
        el.style.zIndex = '1000'
        el.style.touchAction = 'none'

        const handleDragStart = (e: Event) => {
            e.preventDefault()
            e.stopPropagation()
            if (section) {
                setDraggingEndpoint({ sectionId: section.id, endpoint: type })
                setTempBounds({ start: section.startChannel, end: section.endChannel })
            }
        }

        el.addEventListener('mousedown', handleDragStart)
        el.addEventListener('touchstart', handleDragStart)

        return el
    }, [section, setDraggingEndpoint])

    // Handle mouse/touch move during drag
    useEffect(() => {
        if (!map || !draggingEndpoint || !section || !fiberOffsetCoords) return

        const handleDragMove = (lngLat: { lng: number; lat: number }) => {
            const { lng, lat } = lngLat
            const nearestChannel = findNearestChannel(lng, lat)
            if (nearestChannel === null) return

            setTempBounds(prev => {
                if (!prev) return null
                if (draggingEndpoint.endpoint === 'start') {
                    const newStart = Math.min(nearestChannel, prev.end - 1)
                    return { ...prev, start: Math.max(0, newStart) }
                } else {
                    const newEnd = Math.max(nearestChannel, prev.start + 1)
                    return { ...prev, end: Math.min(fiberOffsetCoords.length - 1, newEnd) }
                }
            })
        }

        const handleMouseMove = (e: mapboxgl.MapMouseEvent) => {
            handleDragMove(e.lngLat)
        }

        const handleTouchMove = (e: TouchEvent) => {
            if (e.touches.length === 0) return
            const touch = e.touches[0]
            const canvasPos = map.getCanvas().getBoundingClientRect()
            const lngLat = map.unproject([
                touch.clientX - canvasPos.left,
                touch.clientY - canvasPos.top
            ])
            handleDragMove({ lng: lngLat.lng, lat: lngLat.lat })
        }

        const handleEnd = () => {
            const bounds = tempBoundsRef.current
            if (bounds && section) {
                updateSectionBounds(section.id, bounds.start, bounds.end)
            }
            setDraggingEndpoint(null)
            setTempBounds(null)
        }

        map.on('mousemove', handleMouseMove)
        window.addEventListener('touchmove', handleTouchMove)
        window.addEventListener('mouseup', handleEnd)
        window.addEventListener('touchend', handleEnd)
        map.getCanvas().style.cursor = 'grabbing'

        return () => {
            map.off('mousemove', handleMouseMove)
            window.removeEventListener('touchmove', handleTouchMove)
            window.removeEventListener('mouseup', handleEnd)
            window.removeEventListener('touchend', handleEnd)
            map.getCanvas().style.cursor = ''
        }
    }, [map, draggingEndpoint, section, fiberOffsetCoords, findNearestChannel, updateSectionBounds, setDraggingEndpoint])

    // Create/update markers when section is selected
    useEffect(() => {
        if (startMarkerRef.current) {
            startMarkerRef.current.remove()
            startMarkerRef.current = null
        }
        if (endMarkerRef.current) {
            endMarkerRef.current.remove()
            endMarkerRef.current = null
        }

        if (!map || !section || !fiberOffsetCoords) return

        const startChannel = tempBounds?.start ?? section.startChannel
        const endChannel = tempBounds?.end ?? section.endChannel

        const startCoords = fiberOffsetCoords[startChannel]
        const endCoords = fiberOffsetCoords[endChannel]

        if (startCoords && startCoords[0] != null && startCoords[1] != null &&
            endCoords && endCoords[0] != null && endCoords[1] != null) {
            const startEl = createHandleElement('start')
            startMarkerRef.current = new mapboxgl.Marker({ element: startEl, draggable: false })
                .setLngLat([startCoords[0], startCoords[1]])
                .addTo(map)

            const endEl = createHandleElement('end')
            endMarkerRef.current = new mapboxgl.Marker({ element: endEl, draggable: false })
                .setLngLat([endCoords[0], endCoords[1]])
                .addTo(map)
        }

        return () => {
            startMarkerRef.current?.remove()
            endMarkerRef.current?.remove()
        }
    }, [map, section, fiberOffsetCoords, tempBounds, createHandleElement])

    // Update marker positions during drag
    useEffect(() => {
        if (!fiberOffsetCoords || !tempBounds) return

        const startCoords = fiberOffsetCoords[tempBounds.start]
        const endCoords = fiberOffsetCoords[tempBounds.end]

        if (startMarkerRef.current && startCoords && startCoords[0] != null && startCoords[1] != null) {
            startMarkerRef.current.setLngLat([startCoords[0], startCoords[1]])
        }
        if (endMarkerRef.current && endCoords && endCoords[0] != null && endCoords[1] != null) {
            endMarkerRef.current.setLngLat([endCoords[0], endCoords[1]])
        }
    }, [fiberOffsetCoords, tempBounds])

    return null
}
