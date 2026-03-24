import { useRef, useCallback, useContext, useEffect } from 'react'
import mapboxgl from 'mapbox-gl'
import { COLORS } from '@/lib/theme'
import { findFiber, getSectionCoords, getFiberColor } from '../../data'
import type { Section } from '../../types'
import type { Infrastructure } from '@/types/infrastructure'
import { getSidebarWidth, SidebarRefContext } from '../../hooks/useSidebarWidth'
import { FIBER_WIDTH_EXPR, FIBER_OPACITY_EXPR } from '../mapUtils'

interface UseMapHighlightsParams {
  mapRef: React.RefObject<mapboxgl.Map | null>
  markersRef: React.RefObject<Map<string, mapboxgl.Marker>>
  sectionsRef: React.RefObject<Section[] | undefined>
  fiberColorsRef: React.RefObject<Record<string, string> | undefined>
  sidebarOpenRef: React.RefObject<boolean | undefined>
}

export function useMapHighlights({
  mapRef,
  markersRef,
  sectionsRef,
  fiberColorsRef,
  sidebarOpenRef,
}: UseMapHighlightsParams) {
  const sidebarRef = useContext(SidebarRefContext)
  const highlightTimerRef = useRef<number | null>(null)
  const highlightedMarkerRef = useRef<HTMLElement | null>(null)
  const channelMarkerRef = useRef<mapboxgl.Marker | null>(null)

  const clearHighlight = useCallback(() => {
    const map = mapRef.current
    if (!map) return
    if (highlightTimerRef.current != null) {
      clearInterval(highlightTimerRef.current)
      highlightTimerRef.current = null
    }
    if (map.getLayer('fiber-lines')) {
      map.setPaintProperty('fiber-lines', 'line-width', FIBER_WIDTH_EXPR)
      map.setPaintProperty('fiber-lines', 'line-opacity', FIBER_OPACITY_EXPR)
    }
    const src = map.getSource('hover-highlight') as mapboxgl.GeoJSONSource | undefined
    src?.setData({ type: 'FeatureCollection', features: [] })
    if (channelMarkerRef.current) {
      channelMarkerRef.current.remove()
      channelMarkerRef.current = null
    }
    if (highlightedMarkerRef.current) {
      highlightedMarkerRef.current.style.animation = 'proto-incident-ring 2s ease-in-out infinite'
      highlightedMarkerRef.current = null
    }
  }, [mapRef])

  // Clean up active highlights on unmount (timers + channel marker)
  useEffect(() => {
    return () => {
      clearHighlight()
    }
  }, [clearHighlight])

  const flyTo = useCallback(
    (center: [number, number], zoom = 14) => {
      const sidebarW = !sidebarOpenRef.current ? 0 : getSidebarWidth(sidebarRef)
      mapRef.current?.flyTo({
        center,
        zoom,
        duration: 1500,
        padding: { top: 0, bottom: 0, left: 0, right: sidebarW },
      })
    },
    [mapRef, sidebarOpenRef, sidebarRef],
  )

  const highlightFiber = useCallback(
    (fiberId: string) => {
      const map = mapRef.current
      if (!map || !map.getLayer('fiber-lines')) return
      clearHighlight()
      map.setPaintProperty('fiber-lines', 'line-width', [
        'interpolate',
        ['linear'],
        ['zoom'],
        10,
        ['case', ['==', ['get', 'id'], fiberId], 5, 1.5],
        12,
        ['case', ['==', ['get', 'id'], fiberId], 5, 2],
        14,
        ['case', ['==', ['get', 'id'], fiberId], 5, 2.5],
      ])
      map.setPaintProperty('fiber-lines', 'line-opacity', ['case', ['==', ['get', 'id'], fiberId], 1, 0.15])
      let tick = 0
      highlightTimerRef.current = window.setInterval(() => {
        if (!map.getLayer('fiber-lines')) return
        map.setPaintProperty('fiber-lines', 'line-opacity', [
          'case',
          ['==', ['get', 'id'], fiberId],
          0.5 + 0.5 * Math.abs(Math.sin(tick * 0.6)),
          0.15,
        ])
        tick++
      }, 200)
    },
    [mapRef, clearHighlight],
  )

  const highlightSection = useCallback(
    (sectionId: string) => {
      const map = mapRef.current
      if (!map) return
      clearHighlight()
      const sec = sectionsRef.current?.find(s => s.id === sectionId)
      if (!sec) return
      const secFiber = findFiber(sec.fiberId, sec.direction)
      if (!secFiber) return
      const coords = getSectionCoords(secFiber, sec.startChannel, sec.endChannel)
      if (coords.length < 2) return
      const color = fiberColorsRef.current ? getFiberColor(secFiber, fiberColorsRef.current) : COLORS.fiber.default
      const src = map.getSource('hover-highlight') as mapboxgl.GeoJSONSource | undefined
      src?.setData({
        type: 'FeatureCollection',
        features: [
          {
            type: 'Feature',
            properties: { color },
            geometry: { type: 'LineString', coordinates: coords },
          },
        ],
      })
      let tick = 0
      highlightTimerRef.current = window.setInterval(() => {
        if (map.getLayer('hover-highlight-glow')) {
          map.setPaintProperty('hover-highlight-glow', 'line-opacity', 0.2 + 0.3 * Math.abs(Math.sin(tick * 0.6)))
        }
        tick++
      }, 200)
    },
    [mapRef, clearHighlight, sectionsRef, fiberColorsRef],
  )

  const highlightIncident = useCallback(
    (incidentId: string) => {
      clearHighlight()
      const marker = markersRef.current.get(incidentId)
      if (!marker) return
      const dot = marker.getElement().firstElementChild as HTMLElement | null
      if (!dot) return
      highlightedMarkerRef.current = dot
      dot.style.animation = 'proto-incident-ring 0.6s ease-in-out infinite'
    },
    [clearHighlight, markersRef],
  )

  const highlightStructure = useCallback(
    (structureId: string, structures: Infrastructure[]) => {
      const map = mapRef.current
      if (!map) return
      clearHighlight()
      const structure = structures.find(s => s.id === structureId)
      if (!structure) return
      const sFiber = findFiber(structure.fiberId, structure.direction ?? 0)
      const coords = sFiber ? getSectionCoords(sFiber, structure.startChannel, structure.endChannel) : []
      if (coords.length < 2) return
      const typeColor = COLORS.structure[structure.type].dot
      const src = map.getSource('hover-highlight') as mapboxgl.GeoJSONSource | undefined
      src?.setData({
        type: 'FeatureCollection',
        features: [
          {
            type: 'Feature',
            properties: { color: typeColor },
            geometry: { type: 'LineString', coordinates: coords },
          },
        ],
      })
      let tick = 0
      highlightTimerRef.current = window.setInterval(() => {
        if (map.getLayer('hover-highlight-glow')) {
          map.setPaintProperty('hover-highlight-glow', 'line-opacity', 0.2 + 0.3 * Math.abs(Math.sin(tick * 0.6)))
        }
        tick++
      }, 200)
    },
    [mapRef, clearHighlight],
  )

  const highlightChannel = useCallback(
    (lng: number, lat: number) => {
      const map = mapRef.current
      if (!map) return
      clearHighlight()
      const el = document.createElement('div')
      el.style.cssText = `
        width: 14px; height: 14px; border-radius: 50%;
        background-color: ${COLORS.ui.primary};
        border: 2px solid ${COLORS.map.channelDotBorder};
        animation: proto-channel-pulse 2s ease-in-out infinite;
      `
      channelMarkerRef.current = new mapboxgl.Marker({ element: el, anchor: 'center' }).setLngLat([lng, lat]).addTo(map)
    },
    [mapRef, clearHighlight],
  )

  return {
    flyTo,
    highlightFiber,
    highlightSection,
    highlightIncident,
    highlightStructure,
    highlightChannel,
    clearHighlight,
  }
}
