import { useEffect, useState } from 'react'
import type { Map as MapboxMap, GeoJSONSource } from 'mapbox-gl'
import { COLORS } from '@/lib/theme'
import type { Fiber } from '../../types'
import type { CoverageRange } from '@/api/fibers'
import { onMapReady } from '../mapUtils'
import { MAP_SOURCES, MAP_LAYERS } from './mapTypes'

function buildChannelHelperFeatures(
  fibers: Fiber[],
  fiberOffsetCache: Map<string, [number, number][]>,
  coverageMap: Map<string, CoverageRange[]>,
  offsetIndexToChannel: Map<string, number[]>,
  showFullCable: boolean,
): GeoJSON.Feature[] {
  const features: GeoJSON.Feature[] = []
  for (const fiber of fibers) {
    const coords = fiberOffsetCache.get(fiber.id)
    if (!coords) continue
    const ranges = !showFullCable ? coverageMap.get(fiber.parentCableId) : undefined
    const reverseMap = offsetIndexToChannel.get(fiber.id)
    for (let i = 0; i < coords.length; i++) {
      const c = coords[i]
      if (c[0] == null || c[1] == null) continue
      const channel = reverseMap ? reverseMap[i] : i
      if (ranges && !ranges.some(r => channel >= r.start && channel <= r.end)) continue
      features.push({
        type: 'Feature',
        properties: { color: fiber.color },
        geometry: { type: 'Point', coordinates: [c[0], c[1]] },
      })
    }
  }
  return features
}

export function useMapLayers(
  mapRef: React.RefObject<MapboxMap | null>,
  fibers: Fiber[],
  fiberOffsetCache: Map<string, [number, number][]>,
  coverageMap: Map<string, CoverageRange[]>,
  offsetIndexToChannel: Map<string, number[]>,
  showFullCable: boolean,
) {
  // Signals that map sources/layers have been registered.
  const [sourcesReady, setSourcesReady] = useState(false)

  // One-time source/layer registration — runs once when the map style loads.
  useEffect(() => {
    return onMapReady(mapRef, map => {
      // ── Fiber route layers ──
      map.addSource(MAP_SOURCES.fibers, {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: [] },
      })
      map.addLayer({
        id: MAP_LAYERS.fiberLines,
        type: 'line',
        source: MAP_SOURCES.fibers,
        paint: {
          'line-color': ['get', 'color'],
          'line-width': ['interpolate', ['linear'], ['zoom'], 10, 1.5, 12, 2, 14, 2.5],
          'line-opacity': ['interpolate', ['linear'], ['zoom'], 10, 0.5, 12.5, 0.7, 14, 0.8],
        },
      })

      // ── Channel helper dots (starts empty, populated by the data effect) ──
      map.addSource(MAP_SOURCES.channelHelper, {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: [] },
      })
      map.addLayer({
        id: MAP_LAYERS.channelHelperDots,
        type: 'circle',
        source: MAP_SOURCES.channelHelper,
        layout: { visibility: 'none' },
        paint: {
          'circle-radius': ['interpolate', ['linear'], ['zoom'], 10, 1, 14, 2.5, 17, 4],
          'circle-color': COLORS.map.channelDotBorder,
          'circle-opacity': 0.6,
          'circle-stroke-color': ['get', 'color'],
          'circle-stroke-width': ['interpolate', ['linear'], ['zoom'], 10, 0, 14, 0.5, 17, 1],
        },
      })

      // ── Vehicle dots source ──
      map.addSource(MAP_SOURCES.vehicles, {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: [] },
      })

      // ── Section highlight source ──
      map.addSource(MAP_SOURCES.sectionHighlights, {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: [] },
      })
      map.addLayer({
        id: MAP_LAYERS.sectionHighlight,
        type: 'line',
        source: MAP_SOURCES.sectionHighlights,
        minzoom: 12.5,
        paint: {
          'line-color': ['get', 'color'],
          'line-width': 6,
          'line-opacity': 0.35,
        },
      })

      // ── Hover highlight source ──
      map.addSource(MAP_SOURCES.hoverHighlight, {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: [] },
      })
      map.addLayer({
        id: MAP_LAYERS.hoverHighlightGlow,
        type: 'line',
        source: MAP_SOURCES.hoverHighlight,
        paint: {
          'line-color': COLORS.map.glowLine,
          'line-width': 14,
          'line-opacity': 0.4,
          'line-blur': 7,
        },
      })
      map.addLayer({
        id: MAP_LAYERS.hoverHighlightLine,
        type: 'line',
        source: MAP_SOURCES.hoverHighlight,
        paint: {
          'line-color': ['get', 'color'],
          'line-width': 5,
          'line-opacity': 1,
        },
      })

      // ── Vehicle dots layer (after sections so sections show through) ──
      map.addLayer({
        id: MAP_LAYERS.vehicleDots,
        type: 'circle',
        source: MAP_SOURCES.vehicles,
        minzoom: 12.5,
        paint: {
          'circle-radius': 4,
          'circle-color': ['get', 'color'],
          'circle-opacity': ['get', 'opacity'],
          'circle-stroke-color': COLORS.map.vehicleStroke,
          'circle-stroke-width': 1,
        },
      })

      // ── Pending section preview source ──
      map.addSource(MAP_SOURCES.pendingSection, {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: [] },
      })
      map.addLayer({
        id: MAP_LAYERS.pendingSection,
        type: 'line',
        source: MAP_SOURCES.pendingSection,
        paint: {
          'line-color': COLORS.ui.pending,
          'line-width': 4,
          'line-opacity': 0.6,
          'line-dasharray': [2, 2],
        },
      })

      // ── Pending point marker source ──
      map.addSource(MAP_SOURCES.pendingPoint, {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: [] },
      })
      map.addLayer({
        id: MAP_LAYERS.pendingPoint,
        type: 'circle',
        source: MAP_SOURCES.pendingPoint,
        paint: {
          'circle-radius': 6,
          'circle-color': COLORS.ui.pending,
          'circle-stroke-color': COLORS.map.pendingPointStroke,
          'circle-stroke-width': 2,
        },
      })

      // ── Structure segment lines ──
      map.addSource(MAP_SOURCES.structureLines, {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: [] },
      })
      map.addLayer({
        id: MAP_LAYERS.structureLines,
        type: 'line',
        source: MAP_SOURCES.structureLines,
        paint: {
          'line-color': ['get', 'color'],
          'line-width': 4,
          'line-opacity': 0.6,
        },
      })

      // ── Overview speed-section lines ──
      map.addSource(MAP_SOURCES.speedSections, {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: [] },
      })
      map.addLayer({
        id: MAP_LAYERS.speedSectionLines,
        type: 'line',
        source: MAP_SOURCES.speedSections,
        paint: {
          'line-color': ['get', 'color'],
          'line-width': ['interpolate', ['linear'], ['zoom'], 10, 2.5, 12, 3, 13, 3.5],
          'line-opacity': ['interpolate', ['linear'], ['zoom'], 10, 0.7, 12.5, 0.5, 13.5, 0],
        },
      })

      // ── 3D buildings layer (initially hidden) ──
      const layers = map.getStyle().layers ?? []
      let labelLayerId: string | undefined
      for (const layer of layers) {
        if (layer.type === 'symbol' && (layer as { layout?: { 'text-field'?: unknown } }).layout?.['text-field']) {
          if (!labelLayerId) labelLayerId = layer.id
        }
        if (
          (layer['source-layer'] === 'building' || layer.id.includes('building')) &&
          layer.id !== MAP_LAYERS.buildings3d
        ) {
          map.setLayoutProperty(layer.id, 'visibility', 'none')
        }
      }

      map.addLayer(
        {
          id: MAP_LAYERS.buildings3d,
          source: 'composite',
          'source-layer': 'building',
          filter: ['==', 'extrude', 'true'],
          type: 'fill-extrusion',
          minzoom: 12.5,
          paint: {
            'fill-extrusion-color': COLORS.map.buildingFill,
            'fill-extrusion-height': ['interpolate', ['linear'], ['zoom'], 12.5, 0, 13, ['get', 'height']],
            'fill-extrusion-base': ['interpolate', ['linear'], ['zoom'], 12.5, 0, 13, ['get', 'min_height']],
            'fill-extrusion-opacity': ['interpolate', ['linear'], ['zoom'], 12.5, 0, 13, 0.4, 15, 0.6],
          },
          layout: {
            visibility: 'none',
          },
        },
        labelLayerId,
      )

      setSourcesReady(true)
    })
  }, [mapRef])

  // Populate/update channel helper dots when fiber data or settings change.
  useEffect(() => {
    const map = mapRef.current
    if (!map || !sourcesReady || fibers.length === 0) return
    const src = map.getSource(MAP_SOURCES.channelHelper) as GeoJSONSource | undefined
    if (!src) return
    src.setData({
      type: 'FeatureCollection',
      features: buildChannelHelperFeatures(fibers, fiberOffsetCache, coverageMap, offsetIndexToChannel, showFullCable),
    })
  }, [sourcesReady, mapRef, fibers, fiberOffsetCache, coverageMap, offsetIndexToChannel, showFullCable])
}
