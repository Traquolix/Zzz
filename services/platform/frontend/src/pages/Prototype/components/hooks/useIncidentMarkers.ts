import { useEffect, useRef } from 'react'
import mapboxgl from 'mapbox-gl'
import { COLORS, severityColor } from '@/lib/theme'
import type { ProtoIncident } from '../../types'
import type { MapHandlers } from './mapTypes'

interface UseIncidentMarkersParams {
  mapRef: React.RefObject<mapboxgl.Map | null>
  incidents?: ProtoIncident[]
  incidentClickedRef: React.MutableRefObject<boolean>
  handlersRef: React.RefObject<MapHandlers>
}

export function useIncidentMarkers({ mapRef, incidents, incidentClickedRef, handlersRef }: UseIncidentMarkersParams) {
  const markersRef = useRef<Map<string, mapboxgl.Marker>>(new Map())

  useEffect(() => {
    const map = mapRef.current
    if (!map) return

    markersRef.current.forEach(m => m.remove())
    markersRef.current = new Map()

    if (!incidents?.length) return

    for (const inc of incidents) {
      if (inc.resolved) continue

      const lngLat: [number, number] = inc.location
      const color = severityColor[inc.severity]

      const el = document.createElement('div')
      el.style.cssText = `
        width: 20px; height: 20px; border-radius: 50%;
        display: flex; align-items: center; justify-content: center;
        cursor: pointer;
        background: ${COLORS.map.incidentMarkerBg};
        border: 2px solid ${color};
        box-shadow: 0 0 8px ${COLORS.map.incidentMarkerShadow};
      `
      const dot = document.createElement('div')
      dot.style.cssText = `
        width: 8px; height: 8px; border-radius: 50%;
        background-color: ${color};
        box-shadow: 0 0 6px ${color}cc;
      `
      dot.style.animation = 'proto-incident-ring 2s ease-in-out infinite'
      el.appendChild(dot)
      el.title = inc.title

      el.addEventListener('click', e => {
        e.stopPropagation()
        incidentClickedRef.current = true
        handlersRef.current.onIncidentClick?.(inc.id)
      })

      const marker = new mapboxgl.Marker({ element: el, anchor: 'center' }).setLngLat(lngLat).addTo(map)
      markersRef.current.set(inc.id, marker)
    }

    return () => {
      markersRef.current.forEach(m => m.remove())
      markersRef.current = new Map()
    }
  }, [incidents, mapRef, incidentClickedRef, handlersRef])

  return { markersRef }
}
