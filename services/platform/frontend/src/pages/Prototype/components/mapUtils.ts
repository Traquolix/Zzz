import type { ExpressionSpecification, Map as MapboxMap } from 'mapbox-gl'
import { COLORS } from '@/lib/theme'
import { fibers, fiberOffsetCache, offsetIndexToChannel, getSectionCoords, getFiberColor } from '../data'
import type { Fiber, Section } from '../types'
import type { VehiclePosition } from '../hooks/useVehicleSim'

// ── Map-ready helper ─────────────────────────────────────────────────
// Defers a callback until the map is loaded. Returns a cleanup function.

export function onMapReady(
  mapRef: React.RefObject<MapboxMap | null>,
  callback: (map: MapboxMap) => (() => void) | void,
): () => void {
  const map = mapRef.current
  if (!map) return () => {}

  let cleanup: (() => void) | void
  let settled = false

  if (map.isStyleLoaded()) {
    cleanup = callback(map)
    settled = true
  } else {
    const onLoad = () => {
      settled = true
      cleanup = callback(map)
    }
    map.on('load', onLoad)
    return () => {
      if (!settled) {
        map.off('load', onLoad)
      } else {
        cleanup?.()
      }
    }
  }

  return () => {
    cleanup?.()
  }
}

// ── Nearest fiber point snapping ─────────────────────────────────────

export function findNearestFiberPoint(lngLat: [number, number], maxDistDeg = 0.003) {
  let best: {
    fiberId: string
    direction: 0 | 1
    channel: number
    dist: number
    coord: [number, number]
  } | null = null

  for (const fiber of fibers) {
    // Use offset coords (what's actually rendered on the map) so the dot
    // lands on the visible line rather than the shared cable centerline.
    const offsetCoords = fiberOffsetCache.get(fiber.id)
    const coords = offsetCoords ?? fiber.coordinates
    // The offset cache is null-filtered and shorter than fiber.coordinates,
    // so the loop index is NOT the real channel number. Use the reverse map
    // to translate offset index → real channel.
    const reverseMap = offsetIndexToChannel.get(fiber.id)
    for (let i = 0; i < coords.length; i++) {
      const c = coords[i]
      if (c[0] == null || c[1] == null) continue
      const dx = c[0] - lngLat[0]
      const dy = c[1] - lngLat[1]
      const dist = Math.sqrt(dx * dx + dy * dy)
      if (dist < maxDistDeg && (!best || dist < best.dist)) {
        best = {
          fiberId: fiber.parentCableId,
          direction: fiber.direction,
          channel: reverseMap ? reverseMap[i] : i,
          dist,
          coord: c as [number, number],
        }
      }
    }
  }

  if (!best) return null
  return {
    fiberId: best.fiberId,
    direction: best.direction,
    channel: best.channel,
    lng: best.coord[0],
    lat: best.coord[1],
  }
}

// ── Stable accessor functions for SimpleMeshLayer (avoids re-creation) ──
// deck.gl diffs layer props by reference — these must be module-level
// constants, not inline lambdas, to avoid triggering full layer rebuilds.

export const getPosition = (d: VehiclePosition) => d.position
export const getOrientation = (d: VehiclePosition): [number, number, number] => [0, -d.angle, 0]
export const getScale = (): [number, number, number] => [3, 6, 2]

// ── Zoom expressions for fiber lines ─────────────────────────────────
export const FIBER_WIDTH_EXPR: ExpressionSpecification = ['interpolate', ['linear'], ['zoom'], 10, 1.5, 12, 2, 14, 2.5]
export const FIBER_OPACITY_EXPR: ExpressionSpecification = [
  'interpolate',
  ['linear'],
  ['zoom'],
  10,
  0.5,
  12.5,
  0.7,
  14,
  0.8,
]

// ── Section highlight GeoJSON builder ────────────────────────────────

export function buildSectionHighlightData(
  sections: Section[],
  sectionFiberMap: Map<string, Fiber>,
  fiberColors?: Record<string, string>,
): GeoJSON.FeatureCollection {
  const features = sections
    .map(sec => {
      const sf = sectionFiberMap.get(sec.id)
      if (!sf) return null
      const coords = getSectionCoords(sf, sec.startChannel, sec.endChannel)
      if (coords.length < 2) return null
      const color = fiberColors ? getFiberColor(sf, fiberColors) : (sf.color ?? COLORS.fiber.default)

      return {
        type: 'Feature' as const,
        properties: { color },
        geometry: { type: 'LineString' as const, coordinates: coords },
      }
    })
    .filter(Boolean)

  return { type: 'FeatureCollection', features: features as GeoJSON.Feature[] }
}
