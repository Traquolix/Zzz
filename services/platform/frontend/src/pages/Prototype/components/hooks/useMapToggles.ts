import { useEffect } from 'react'
import type { Map as MapboxMap, GeoJSONSource } from 'mapbox-gl'
import { fibers, fiberRenderCache, getFiberColor } from '../../data'
import type { Fiber, Section, PendingPoint } from '../../types'
import { buildSectionHighlightData } from '../mapUtils'

interface UseMapTogglesParams {
  mapRef: React.RefObject<MapboxMap | null>
  sections?: Section[]
  fiberColors?: Record<string, string>
  pendingPoint?: PendingPoint | null
  hideFibersInOverview?: boolean
  show3DBuildings?: boolean
  showChannelHelper?: boolean
  sectionCreationMode?: boolean
  sectionFibersRef: React.RefObject<Map<string, Fiber>>
  fiberColorsRef: React.RefObject<Record<string, string> | undefined>
  overviewRef: React.RefObject<boolean>
}

export function useMapToggles({
  mapRef,
  sections,
  fiberColors,
  pendingPoint,
  hideFibersInOverview,
  show3DBuildings,
  showChannelHelper,
  sectionCreationMode,
  sectionFibersRef,
  fiberColorsRef,
  overviewRef,
}: UseMapTogglesParams) {
  // 1. Section highlights
  useEffect(() => {
    const map = mapRef.current
    if (!map) return

    const apply = () => {
      const source = map.getSource('section-highlights') as GeoJSONSource | undefined
      if (!source) return
      source.setData(buildSectionHighlightData(sections ?? [], sectionFibersRef.current, fiberColorsRef.current))
    }

    apply()
    const onIdle = () => apply()
    map.once('idle', onIdle)
    return () => {
      map.off('idle', onIdle)
    }
  }, [mapRef, sections, fiberColors, sectionFibersRef, fiberColorsRef])

  // 2. Pending point marker
  useEffect(() => {
    const map = mapRef.current
    if (!map) return

    const apply = () => {
      const pointSource = map.getSource('pending-point') as GeoJSONSource | undefined
      if (!pointSource) return

      if (pendingPoint) {
        pointSource.setData({
          type: 'FeatureCollection',
          features: [
            {
              type: 'Feature',
              properties: {},
              geometry: { type: 'Point', coordinates: [pendingPoint.lng, pendingPoint.lat] },
            },
          ],
        })
      } else {
        pointSource.setData({ type: 'FeatureCollection', features: [] })
      }

      const sectionSource = map.getSource('pending-section') as GeoJSONSource | undefined
      if (sectionSource && !pendingPoint) {
        sectionSource.setData({ type: 'FeatureCollection', features: [] })
      }
    }

    if (map.isStyleLoaded()) {
      apply()
    } else {
      map.once('idle', apply)
      return () => {
        map.off('idle', apply)
      }
    }
  }, [mapRef, pendingPoint])

  // 3. Fiber line colors
  useEffect(() => {
    const map = mapRef.current
    if (!map || !fiberColors) return
    const src = map.getSource('fibers') as GeoJSONSource | undefined
    if (!src) return
    const features: GeoJSON.Feature[] = []
    for (const fiber of fibers) {
      const coords = fiberRenderCache.get(fiber.id)
      if (!coords) continue
      features.push({
        type: 'Feature' as const,
        properties: { id: fiber.id, name: fiber.name, color: getFiberColor(fiber, fiberColors) },
        geometry: { type: 'LineString' as const, coordinates: coords },
      })
    }
    src.setData({ type: 'FeatureCollection', features })
  }, [mapRef, fiberColors])

  // 4. Fiber visibility in overview
  useEffect(() => {
    const map = mapRef.current
    if (!map || !map.isStyleLoaded()) return
    const hide = hideFibersInOverview && overviewRef.current
    if (map.getLayer('fiber-lines')) {
      map.setLayoutProperty('fiber-lines', 'visibility', hide ? 'none' : 'visible')
    }
  }, [mapRef, hideFibersInOverview, overviewRef])

  // 5. 3D buildings
  useEffect(() => {
    const map = mapRef.current
    if (!map || !map.isStyleLoaded()) return
    if (map.getLayer('3d-buildings')) {
      map.setLayoutProperty('3d-buildings', 'visibility', show3DBuildings ? 'visible' : 'none')
    }
  }, [mapRef, show3DBuildings])

  // 6. Channel helper dots
  useEffect(() => {
    const map = mapRef.current
    if (!map || !map.isStyleLoaded()) return
    if (map.getLayer('channel-helper-dots')) {
      map.setLayoutProperty('channel-helper-dots', 'visibility', showChannelHelper ? 'visible' : 'none')
    }
  }, [mapRef, showChannelHelper])

  // 7. Cursor mode
  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    map.getCanvas().style.cursor = sectionCreationMode ? 'crosshair' : ''
  }, [mapRef, sectionCreationMode])
}
