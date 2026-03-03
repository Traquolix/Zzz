import { useEffect, useMemo, useRef } from 'react'
import mapboxgl from 'mapbox-gl'
import { useMap } from '../MapContext'
import { useIncidents } from '@/hooks/useIncidents'
import { useFibers } from '@/hooks/useFibers'
import { SEVERITY_HEX } from '@/constants/incidents'

// Create a DOM element for incident marker
function createIncidentMarkerEl(type: string, severity: string, isRecent: boolean): HTMLDivElement {
    const size = isRecent ? 26 : 24
    const color = SEVERITY_HEX[severity] || '#ef4444'

    const el = document.createElement('div')
    el.style.width = `${size}px`
    el.style.height = `${size}px`
    el.style.borderRadius = '6px'
    el.style.backgroundColor = color
    el.style.border = `${isRecent ? 2.5 : 2}px solid white`
    el.style.display = 'flex'
    el.style.alignItems = 'center'
    el.style.justifyContent = 'center'
    el.style.boxShadow = isRecent
        ? `0 0 8px ${color}, 0 2px 4px rgba(0,0,0,0.2)`
        : '0 2px 4px rgba(0,0,0,0.2)'
    el.style.cursor = 'pointer'
    el.style.pointerEvents = 'auto'
    el.style.zIndex = '100' // Above vehicle markers, below info panels

    // Add icon based on type
    const icon = document.createElement('span')
    icon.style.color = 'white'
    icon.style.fontSize = '12px'
    icon.style.fontWeight = 'bold'
    icon.style.lineHeight = '1'

    switch (type) {
        case 'slowdown':
            icon.innerHTML = '&#8595;' // down arrow
            icon.style.fontSize = '10px'
            break
        case 'congestion':
            icon.innerHTML = '&#9776;' // triple bar
            icon.style.fontSize = '10px'
            break
        case 'accident':
            icon.textContent = '!'
            break
        case 'anomaly':
            icon.textContent = '?'
            break
        default:
            icon.textContent = '!'
    }

    el.appendChild(icon)
    return el
}

export function IncidentLayer() {
    const map = useMap()
    const { incidents } = useIncidents()
    const { getPosition } = useFibers()
    const markersRef = useRef<Map<string, mapboxgl.Marker>>(new Map())

    // Find the most recent incident
    const mostRecentId = useMemo(() =>
        incidents
            .filter(i => i.status === 'active')
            .sort((a, b) => new Date(b.detectedAt).getTime() - new Date(a.detectedAt).getTime())[0]?.id,
        [incidents]
    )

    // Update markers when incidents change
    useEffect(() => {
        const markers = markersRef.current
        const activeIds = new Set<string>()

        // Add/update markers for active incidents
        incidents
            .filter(i => i.status === 'active')
            .forEach(incident => {
                const pos = getPosition(incident.fiberLine, incident.channel, 0)
                if (!pos) return

                activeIds.add(incident.id)
                const isRecent = incident.id === mostRecentId

                let marker = markers.get(incident.id)

                if (!marker) {
                    // Create new marker
                    const el = createIncidentMarkerEl(incident.type, incident.severity, isRecent)
                    marker = new mapboxgl.Marker({ element: el })
                        .setLngLat([pos.lng, pos.lat])
                        .addTo(map)
                    markers.set(incident.id, marker)
                } else {
                    // Update position
                    marker.setLngLat([pos.lng, pos.lat])

                    // Update styles in-place when recent status changes (avoids DOM churn)
                    const el = marker.getElement()
                    const currentIsRecent = el.style.boxShadow.includes('0 0 8px')
                    if (currentIsRecent !== isRecent) {
                        const color = SEVERITY_HEX[incident.severity] || '#ef4444'
                        const size = isRecent ? 26 : 24
                        el.style.width = `${size}px`
                        el.style.height = `${size}px`
                        el.style.border = `${isRecent ? 2.5 : 2}px solid white`
                        el.style.boxShadow = isRecent
                            ? `0 0 8px ${color}, 0 2px 4px rgba(0,0,0,0.2)`
                            : '0 2px 4px rgba(0,0,0,0.2)'
                    }
                }
            })

        // Remove markers for incidents that are no longer active
        for (const [id, marker] of markers) {
            if (!activeIds.has(id)) {
                marker.remove()
                markers.delete(id)
            }
        }
    }, [map, incidents, getPosition, mostRecentId])

    // Cleanup on unmount
    useEffect(() => {
        const markers = markersRef.current
        return () => {
            markers.forEach(m => m.remove())
            markers.clear()
        }
    }, [])

    return null
}
