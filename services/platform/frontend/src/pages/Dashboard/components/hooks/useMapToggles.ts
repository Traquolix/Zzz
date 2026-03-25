import { useEffect } from 'react'
import type { Map as MapboxMap, GeoJSONSource } from 'mapbox-gl'
import { fibers, fiberRenderCache, getFiberColor } from '../../data'
import type { Fiber, Section, PendingPoint } from '../../types'
import { buildSectionHighlightData } from '../mapUtils'
import { MAP_SOURCES, MAP_LAYERS } from './mapTypes'

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
      const source = map.getSource(MAP_SOURCES.sectionHighlights) as GeoJSONSource | undefined
      if (!source) return
      source.setData(buildSectionHighlightData(sections ?? [], sectionFibersRef.current, fiberColorsRef.current))
    }

    if (map.isStyleLoaded()) {
      apply()
    }
    // Always also apply on next idle — covers races where getSource() returns
    // undefined during flyTo transitions or style reloads
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
      const pointSource = map.getSource(MAP_SOURCES.pendingPoint) as GeoJSONSource | undefined
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

      const sectionSource = map.getSource(MAP_SOURCES.pendingSection) as GeoJSONSource | undefined
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
    const src = map.getSource(MAP_SOURCES.fibers) as GeoJSONSource | undefined
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
    if (map.getLayer(MAP_LAYERS.fiberLines)) {
      map.setLayoutProperty(MAP_LAYERS.fiberLines, 'visibility', hide ? 'none' : 'visible')
    }
    // Two paths control fiber visibility: the zoom handler in useMapInteractions
    // toggles on zoom changes (reading hideFibersRef), and this effect toggles on
    // prop changes (reading overviewRef). overviewRef is a mutable ref set by the
    // zoom handler — always current when read synchronously — so omitting it from
    // deps is correct; including it would be a no-op (refs don't trigger re-renders).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mapRef, hideFibersInOverview])

  // 5. 3D buildings
  useEffect(() => {
    const map = mapRef.current
    if (!map || !map.isStyleLoaded()) return
    if (map.getLayer(MAP_LAYERS.buildings3d)) {
      map.setLayoutProperty(MAP_LAYERS.buildings3d, 'visibility', show3DBuildings ? 'visible' : 'none')
    }
  }, [mapRef, show3DBuildings])

  // 6. Channel helper dots
  useEffect(() => {
    const map = mapRef.current
    if (!map || !map.isStyleLoaded()) return
    if (map.getLayer(MAP_LAYERS.channelHelperDots)) {
      map.setLayoutProperty(MAP_LAYERS.channelHelperDots, 'visibility', showChannelHelper ? 'visible' : 'none')
    }
  }, [mapRef, showChannelHelper])

  // 7. Cursor mode
  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    map.getCanvas().style.cursor = sectionCreationMode ? 'crosshair' : ''
  }, [mapRef, sectionCreationMode])
}
