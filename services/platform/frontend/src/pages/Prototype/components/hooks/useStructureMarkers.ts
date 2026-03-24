import { useEffect, useRef } from 'react'
import mapboxgl from 'mapbox-gl'
import { COLORS, shmStatusColors } from '@/lib/theme'
import { findFiber, getSectionCoords, channelToCoord } from '../../data'
import type { Infrastructure, SHMStatus } from '@/types/infrastructure'
import { MAP_SOURCES } from './mapTypes'

interface UseStructureMarkersParams {
  mapRef: React.RefObject<mapboxgl.Map | null>
  structures?: Infrastructure[]
  structureStatuses?: Map<string, SHMStatus>
  showStructuresOnMap?: boolean
  showStructureLabels?: boolean
  selectedStructureId?: string | null
  onStructureClickRef: React.RefObject<((id: string) => void) | undefined>
}

export function useStructureMarkers({
  mapRef,
  structures,
  structureStatuses,
  showStructuresOnMap,
  showStructureLabels,
  selectedStructureId,
  onStructureClickRef,
}: UseStructureMarkersParams) {
  const structureMarkersRef = useRef<Map<string, mapboxgl.Marker>>(new Map())

  // Update structure line source
  // NOTE: switched from onMapReady (fires once on load) to isStyleLoaded + idle
  // to match the pattern used by useMapToggles and handle flyTo/style-reload races
  useEffect(() => {
    const map = mapRef.current
    if (!map) return

    const apply = () => {
      const src = map.getSource(MAP_SOURCES.structureLines) as mapboxgl.GeoJSONSource | undefined
      if (!src) return

      if (!showStructuresOnMap || !structures?.length) {
        src.setData({ type: 'FeatureCollection', features: [] })
        return
      }

      const features = structures
        .map(s => {
          const sFiber = findFiber(s.fiberId, s.direction ?? 0)
          const coords = sFiber ? getSectionCoords(sFiber, s.startChannel, s.endChannel) : []
          if (coords.length < 2) return null
          const color = COLORS.structure[s.type].dot
          return {
            type: 'Feature' as const,
            properties: { color, id: s.id },
            geometry: { type: 'LineString' as const, coordinates: coords },
          }
        })
        .filter(Boolean)

      src.setData({ type: 'FeatureCollection', features: features as GeoJSON.Feature[] })
    }

    if (map.isStyleLoaded()) {
      apply()
    }
    // Also apply on next idle — covers races where getSource() returns
    // undefined during flyTo transitions or style reloads
    const onIdle = () => apply()
    map.once('idle', onIdle)
    return () => {
      map.off('idle', onIdle)
    }
  }, [mapRef, structures, showStructuresOnMap])

  // Update structure label markers
  useEffect(() => {
    const map = mapRef.current
    if (!map) return

    const markers = structureMarkersRef.current
    markers.forEach(m => m.remove())
    markers.clear()

    if (!showStructureLabels || !structures?.length) return

    for (const s of structures) {
      const sFiber = findFiber(s.fiberId, s.direction ?? 0)
      const midChannel = Math.floor((s.startChannel + s.endChannel) / 2)
      const coord = sFiber ? channelToCoord(sFiber, midChannel) : null
      if (!coord) continue

      const status = structureStatuses?.get(s.id)
      const statusDotColor = status ? (shmStatusColors[status.status] ?? COLORS.shmChart.axis) : COLORS.shmChart.axis
      const isSelected = selectedStructureId === s.id

      const imageHtml = s.imageUrl
        ? `<img src="${s.imageUrl}" style="width:100%;height:48px;object-fit:cover;border-radius:6px 6px 0 0;display:block;" />`
        : ''

      const el = document.createElement('div')
      el.className = 'prototype'
      el.innerHTML = `
        <div style="
          background: var(--proto-surface, #1e293b);
          border: 1px solid ${isSelected ? 'var(--proto-accent, #6366f1)' : 'var(--proto-border, #334155)'};
          border-radius: 8px;
          cursor: pointer;
          overflow: hidden;
          box-shadow: 0 4px 12px rgba(0,0,0,0.4);
          white-space: nowrap;
          min-width: 100px;
          max-width: 160px;
        ">
          ${imageHtml}
          <div style="padding:6px 10px;display:flex;align-items:center;gap:6px;">
            <span style="width:6px;height:6px;border-radius:50%;background:${statusDotColor};flex-shrink:0;"></span>
            <span style="font-size:11px;color:${COLORS.timeSeries.tooltipText};font-weight:500;overflow:hidden;text-overflow:ellipsis;">${s.name}</span>
            <span style="font-size:10px;color:${COLORS.shmChart.axis};flex-shrink:0;">${s.type}</span>
          </div>
        </div>
      `

      el.addEventListener('click', e => {
        e.stopPropagation()
        onStructureClickRef.current?.(s.id)
      })

      const marker = new mapboxgl.Marker({ element: el, anchor: 'bottom' }).setLngLat(coord).addTo(map)
      structureMarkersRef.current.set(s.id, marker)
    }

    return () => {
      markers.forEach(m => m.remove())
      markers.clear()
    }
  }, [mapRef, structures, structureStatuses, showStructureLabels, selectedStructureId, onStructureClickRef])
}
