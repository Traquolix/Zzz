import { useEffect, useRef, useState } from 'react'
import mapboxgl from 'mapbox-gl'
import 'mapbox-gl/dist/mapbox-gl.css'
import { MAPBOX_TOKEN } from '@/config/mapbox'
import { useFibers } from '@/hooks/useFibers'
import type { Infrastructure, SelectedInfrastructure } from '@/types/infrastructure'

mapboxgl.accessToken = MAPBOX_TOKEN

const TYPE_COLORS: Record<string, string> = {
    bridge: '#f59e0b',
    tunnel: '#6366f1'
}

type Props = {
    infrastructures: Infrastructure[]
    selectedInfrastructure: SelectedInfrastructure | null
    onSelect: (infra: Infrastructure) => void
    className?: string
}

export function SHMMap({ infrastructures, selectedInfrastructure, onSelect, className }: Props) {
    const mapContainerRef = useRef<HTMLDivElement>(null)
    const mapRef = useRef<mapboxgl.Map | null>(null)
    const markersRef = useRef<Map<string, mapboxgl.Marker>>(new Map())
    const [ready, setReady] = useState(false)

    const { fibers } = useFibers()

    // Initialize map
    useEffect(() => {
        if (!mapContainerRef.current) return

        const map = new mapboxgl.Map({
            container: mapContainerRef.current,
            style: 'mapbox://styles/mapbox/light-v11',
            center: [7.26, 43.7],
            zoom: 12,
            pitch: 0,
            bearing: 0,
            attributionControl: false,
        })

        mapRef.current = map

        map.addControl(new mapboxgl.NavigationControl({ showCompass: false }), 'top-right')

        map.once('style.load', () => {
            setReady(true)
        })

        return () => {
            setReady(false)
            map.remove()
            mapRef.current = null
        }
    }, [])

    // Add/update markers when infrastructures or fibers change
    useEffect(() => {
        if (!ready || !mapRef.current || fibers.length === 0) return

        const map = mapRef.current
        const currentIds = new Set(infrastructures.map(i => i.id))

        // Remove old markers
        for (const [id, marker] of markersRef.current) {
            if (!currentIds.has(id)) {
                marker.remove()
                markersRef.current.delete(id)
            }
        }

        // Add new markers
        for (const infra of infrastructures) {
            if (markersRef.current.has(infra.id)) continue

            // Find the fiber and get midpoint coordinates
            // Infrastructure stores the physical cable ID (e.g., "carros")
            // Fibers are directional with IDs like "carros:0", so match on parentFiberId
            const fiber = fibers.find(f => f.parentFiberId === infra.fiberId)
            if (!fiber) continue

            const midChannel = Math.floor((infra.startChannel + infra.endChannel) / 2)
            const coords = fiber.coordinates[midChannel]
            if (!coords || coords[0] == null || coords[1] == null) continue

            const [lng, lat] = coords
            const color = TYPE_COLORS[infra.type] || '#6b7280'

            // Create marker element
            const el = document.createElement('div')
            el.className = 'flex items-center gap-1.5 px-2 py-1 rounded-md text-white text-xs font-medium shadow-md cursor-pointer'
            el.style.backgroundColor = color

            // Status dot (green for nominal)
            const statusDot = `<div class="w-2 h-2 rounded-full bg-emerald-400 flex-shrink-0"></div>`

            // Icon
            const iconSvg = `<svg class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                <path stroke-linecap="round" stroke-linejoin="round" d="M2.25 21h19.5m-18-18v18m10.5-18v18m6-13.5V21M6.75 6.75h.75m-.75 3h.75m-.75 3h.75m3-6h.75m-.75 3h.75m-.75 3h.75M6.75 21v-3.375c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125V21M3 3h12m-.75 4.5H21m-3.75 3H21m-3.75 3H21"/>
            </svg>`
            el.innerHTML = iconSvg + statusDot + `<span>${infra.name}</span>`

            el.addEventListener('click', (e) => {
                e.stopPropagation()
                onSelect(infra)
            })

            const marker = new mapboxgl.Marker({ element: el, anchor: 'bottom', offset: [0, -5] })
                .setLngLat([lng, lat])
                .addTo(map)

            markersRef.current.set(infra.id, marker)
        }

        // Fit bounds to show all markers
        if (markersRef.current.size > 0) {
            const bounds = new mapboxgl.LngLatBounds()
            for (const marker of markersRef.current.values()) {
                bounds.extend(marker.getLngLat())
            }
            map.fitBounds(bounds, { padding: 80, maxZoom: 14 })
        }
    }, [ready, infrastructures, fibers, onSelect])

    // Update marker styling when selection changes
    useEffect(() => {
        for (const [id, marker] of markersRef.current) {
            const el = marker.getElement()
            const isSelected = selectedInfrastructure?.id === id

            if (isSelected) {
                el.style.boxShadow = '0 0 0 3px white, 0 4px 12px rgba(0,0,0,0.3)'
                el.style.zIndex = '10'
            } else {
                el.style.boxShadow = '0 2px 6px rgba(0,0,0,0.2)'
                el.style.zIndex = '1'
            }
        }
    }, [selectedInfrastructure])

    // Resize map when container changes (debounced to prevent flashing)
    useEffect(() => {
        if (!mapRef.current || !mapContainerRef.current) return

        let resizeTimeout: ReturnType<typeof setTimeout> | null = null

        const resizer = new ResizeObserver(() => {
            // Debounce resize calls to prevent rapid consecutive renders
            if (resizeTimeout) clearTimeout(resizeTimeout)
            resizeTimeout = setTimeout(() => {
                mapRef.current?.resize()
            }, 100)
        })
        resizer.observe(mapContainerRef.current)

        return () => {
            if (resizeTimeout) clearTimeout(resizeTimeout)
            resizer.disconnect()
        }
    }, [ready])

    return (
        <div ref={mapContainerRef} className={`w-full h-full ${className ?? ''}`} />
    )
}
