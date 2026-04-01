import { useEffect, useMemo } from 'react'
import type { Map as MapboxMap, GeoJSONSource } from 'mapbox-gl'
import { getFiberColor } from '../../data'
import type { Fiber, Section, PendingPoint } from '../../types'
import type { CoverageRange } from '@/api/fibers'
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
  showFullCable?: boolean
  coverageMap?: Map<string, CoverageRange[]>
  sectionCreationMode?: boolean
  sectionFibersRef: React.RefObject<Map<string, Fiber>>
  fiberColorsRef: React.RefObject<Record<string, string> | undefined>
  overviewRef: React.RefObject<boolean>
  fibers: Fiber[]
  fiberRenderCache: Map<string, [number, number][]>
  buildCoverageRenderCache: (cm: Map<string, CoverageRange[]>) => Map<string, [number, number][][]>
  getSectionCoordsRef: React.RefObject<(fiber: Fiber, startChannel: number, endChannel: number) => [number, number][]>
}

/** Build GeoJSON features for fiber lines, optionally clipped to data coverage. */
function buildFiberFeatures(
  fibers: Fiber[],
  fiberRenderCache: Map<string, [number, number][]>,
  fiberColors: Record<string, string> | undefined,
  showFullCable: boolean,
  coverageRenderCache: Map<string, [number, number][][]>,
): GeoJSON.Feature[] {
  const features: GeoJSON.Feature[] = []
  for (const fiber of fibers) {
    const color = fiberColors ? getFiberColor(fiber, fiberColors) : fiber.color
    const props = { id: fiber.id, name: fiber.name, color }

    if (showFullCable) {
      // Full cable rendering (toggle is on)
      const coords = fiberRenderCache.get(fiber.id)
      if (!coords) continue
      features.push({
        type: 'Feature' as const,
        properties: props,
        geometry: { type: 'LineString' as const, coordinates: coords },
      })
    } else if (coverageRenderCache.has(fiber.id)) {
      // Render only the data-covered segments
      const segments = coverageRenderCache.get(fiber.id)!
      if (segments.length === 1) {
        features.push({
          type: 'Feature' as const,
          properties: props,
          geometry: { type: 'LineString' as const, coordinates: segments[0] },
        })
      } else {
        features.push({
          type: 'Feature' as const,
          properties: props,
          geometry: { type: 'MultiLineString' as const, coordinates: segments },
        })
      }
    }
    // If no coverage data and showFullCable is off, skip this fiber
  }
  return features
}

export function useMapToggles({
  mapRef,
  sections,
  fiberColors,
  pendingPoint,
  hideFibersInOverview,
  show3DBuildings,
  showChannelHelper,
  showFullCable,
  coverageMap,
  sectionCreationMode,
  sectionFibersRef,
  fiberColorsRef,
  overviewRef,
  fibers,
  fiberRenderCache,
  buildCoverageRenderCache,
  getSectionCoordsRef,
}: UseMapTogglesParams) {
  // Memoize coverage render cache so it's only rebuilt when coverageMap changes
  const coverageRenderCache = useMemo(
    () => (coverageMap && coverageMap.size > 0 ? buildCoverageRenderCache(coverageMap) : new Map()),
    [coverageMap, buildCoverageRenderCache],
  )

  // 1. Section highlights
  useEffect(() => {
    const map = mapRef.current
    if (!map) return

    const apply = () => {
      const source = map.getSource(MAP_SOURCES.sectionHighlights) as GeoJSONSource | undefined
      if (!source) return
      source.setData(
        buildSectionHighlightData(
          sections ?? [],
          sectionFibersRef.current,
          fiberColorsRef.current,
          getSectionCoordsRef.current,
        ),
      )
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
  }, [mapRef, sections, fiberColors, sectionFibersRef, fiberColorsRef, getSectionCoordsRef])

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

  // 3. Fiber line rendering (colors + coverage toggle)
  useEffect(() => {
    const map = mapRef.current
    if (!map || !fiberColors) return

    const apply = () => {
      const src = map.getSource(MAP_SOURCES.fibers) as GeoJSONSource | undefined
      if (!src) return
      const features = buildFiberFeatures(
        fibers,
        fiberRenderCache,
        fiberColors,
        showFullCable ?? false,
        coverageRenderCache,
      )
      src.setData({ type: 'FeatureCollection', features })
    }

    if (map.isStyleLoaded()) {
      apply()
    }
    const onIdle = () => apply()
    map.once('idle', onIdle)
    return () => {
      map.off('idle', onIdle)
    }
  }, [mapRef, fiberColors, showFullCable, coverageRenderCache, fibers, fiberRenderCache])

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
