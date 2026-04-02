import type { ExpressionSpecification, Map as MapboxMap } from 'mapbox-gl'
import { COLORS } from '@/lib/theme'
import { getFiberColor } from '../data'
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
      map.off('load', onLoad) // always remove listener
      if (settled) {
        cleanup?.()
      }
    }
  }

  return () => {
    cleanup?.()
  }
}

// ── Stable accessor functions for SimpleMeshLayer (avoids re-creation) ──
// deck.gl diffs layer props by reference — these must be module-level
// constants, not inline lambdas, to avoid triggering full layer rebuilds.
// Exception: getVehicleColor (in useRenderLoop) must be a closure to access
// runtime state; it is stable for the lifetime of the onMapReady callback.

export const getPosition = (d: VehiclePosition) => d.position
export const getOrientation = (d: VehiclePosition): [number, number, number] => [0, -d.angle, 0]
export const getScale = (d: VehiclePosition): [number, number, number] => (d.nTrucks > 0 ? [3, 9, 4] : [3, 6, 2])

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
  fiberColors: Record<string, string> | undefined,
  getSectionCoords: (fiber: Fiber, startChannel: number, endChannel: number) => [number, number][],
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
