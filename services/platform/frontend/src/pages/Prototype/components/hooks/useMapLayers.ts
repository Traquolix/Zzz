import { useEffect } from 'react'
import type { Map as MapboxMap } from 'mapbox-gl'
import { COLORS } from '@/lib/theme'
import { fibers, fiberOffsetCache, fiberRenderCache } from '../../data'
import { onMapReady } from '../mapUtils'

export function useMapLayers(mapRef: React.RefObject<MapboxMap | null>) {
  useEffect(() => {
    return onMapReady(mapRef, map => {
      // ── Fiber route layers ──
      const fiberFeatures: GeoJSON.Feature[] = []
      for (const fiber of fibers) {
        const coords = fiberRenderCache.get(fiber.id)
        if (!coords) continue
        fiberFeatures.push({
          type: 'Feature' as const,
          properties: { id: fiber.id, name: fiber.name, color: fiber.color },
          geometry: { type: 'LineString' as const, coordinates: coords },
        })
      }
      map.addSource('fibers', {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: fiberFeatures },
      })
      map.addLayer({
        id: 'fiber-lines',
        type: 'line',
        source: 'fibers',
        paint: {
          'line-color': ['get', 'color'],
          'line-width': ['interpolate', ['linear'], ['zoom'], 10, 1.5, 12, 2, 14, 2.5],
          'line-opacity': ['interpolate', ['linear'], ['zoom'], 10, 0.5, 12.5, 0.7, 14, 0.8],
        },
      })

      // ── Channel helper dots ──
      const channelFeatures: GeoJSON.Feature[] = []
      for (const fiber of fibers) {
        const coords = fiberOffsetCache.get(fiber.id)
        if (!coords) continue
        for (let ch = 0; ch < coords.length; ch++) {
          const c = coords[ch]
          if (c[0] == null || c[1] == null) continue
          channelFeatures.push({
            type: 'Feature',
            properties: { color: fiber.color },
            geometry: { type: 'Point', coordinates: [c[0], c[1]] },
          })
        }
      }
      map.addSource('channel-helper', {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: channelFeatures },
      })
      map.addLayer({
        id: 'channel-helper-dots',
        type: 'circle',
        source: 'channel-helper',
        layout: { visibility: 'none' },
        paint: {
          'circle-radius': ['interpolate', ['linear'], ['zoom'], 10, 1, 14, 2.5, 17, 4],
          'circle-color': ['get', 'color'],
          'circle-opacity': 0.6,
        },
      })

      // ── Vehicle dots source ──
      map.addSource('vehicles', {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: [] },
      })

      // ── Section highlight source ──
      map.addSource('section-highlights', {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: [] },
      })
      map.addLayer({
        id: 'section-highlight-layer',
        type: 'line',
        source: 'section-highlights',
        minzoom: 12.5,
        layout: { visibility: 'none' },
        paint: {
          'line-color': ['get', 'color'],
          'line-width': 6,
          'line-opacity': 0.35,
        },
      })

      // ── Hover highlight source ──
      map.addSource('hover-highlight', {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: [] },
      })
      map.addLayer({
        id: 'hover-highlight-glow',
        type: 'line',
        source: 'hover-highlight',
        paint: {
          'line-color': COLORS.map.glowLine,
          'line-width': 14,
          'line-opacity': 0.4,
          'line-blur': 7,
        },
      })
      map.addLayer({
        id: 'hover-highlight-line',
        type: 'line',
        source: 'hover-highlight',
        paint: {
          'line-color': ['get', 'color'],
          'line-width': 5,
          'line-opacity': 1,
        },
      })

      // ── Vehicle dots layer (after sections so sections show through) ──
      map.addLayer({
        id: 'vehicle-dots',
        type: 'circle',
        source: 'vehicles',
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
      map.addSource('pending-section', {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: [] },
      })
      map.addLayer({
        id: 'pending-section-layer',
        type: 'line',
        source: 'pending-section',
        paint: {
          'line-color': COLORS.ui.pending,
          'line-width': 4,
          'line-opacity': 0.6,
          'line-dasharray': [2, 2],
        },
      })

      // ── Pending point marker source ──
      map.addSource('pending-point', {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: [] },
      })
      map.addLayer({
        id: 'pending-point-layer',
        type: 'circle',
        source: 'pending-point',
        paint: {
          'circle-radius': 6,
          'circle-color': COLORS.ui.pending,
          'circle-stroke-color': COLORS.map.pendingPointStroke,
          'circle-stroke-width': 2,
        },
      })

      // ── Structure segment lines ──
      map.addSource('structure-lines', {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: [] },
      })
      map.addLayer({
        id: 'structure-lines-layer',
        type: 'line',
        source: 'structure-lines',
        paint: {
          'line-color': ['get', 'color'],
          'line-width': 4,
          'line-opacity': 0.6,
        },
      })

      // ── Overview speed-section lines ──
      map.addSource('speed-sections', {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: [] },
      })
      map.addLayer({
        id: 'speed-section-lines',
        type: 'line',
        source: 'speed-sections',
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
        if ((layer['source-layer'] === 'building' || layer.id.includes('building')) && layer.id !== '3d-buildings') {
          map.setLayoutProperty(layer.id, 'visibility', 'none')
        }
      }

      map.addLayer(
        {
          id: '3d-buildings',
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
    })
  }, [mapRef])
}
