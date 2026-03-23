/**
 * Geographic utilities for polyline offset calculations.
 * Used to render dual-direction fiber lines on the map.
 */

import type { FiberLine } from '@/types/fiber'

/** Perpendicular offset distance in meters for each direction's line. */
const DIRECTION_OFFSET_METERS = 12

const METERS_PER_DEG_LAT = 111320

/**
 * Filter out null/invalid coordinates, returning only valid [lng, lat] pairs.
 * Used before passing coordinates to Mapbox or offset calculations.
 */
function filterValidCoords(coords: ([number, number] | [null, null])[]): [number, number][] {
  return coords.filter((c): c is [number, number] => c[0] != null && c[1] != null)
}

/**
 * Shift a polyline perpendicular to its direction by `offsetMeters`.
 * Positive offset shifts right (relative to forward direction), negative shifts left.
 *
 * Uses flat-earth approximation (adequate for small offsets like 10-15m).
 * Null/invalid coordinates are filtered out before processing.
 */
function offsetCoordinates(coords: ([number, number] | [null, null])[], offsetMeters: number): [number, number][] {
  const valid = filterValidCoords(coords)
  if (valid.length < 2) return valid

  const result: [number, number][] = []

  for (let i = 0; i < valid.length; i++) {
    const [lng, lat] = valid[i]
    const metersPerDegLng = METERS_PER_DEG_LAT * Math.cos((lat * Math.PI) / 180)

    // Compute perpendicular direction at this vertex
    let nx = 0,
      ny = 0

    if (i === 0) {
      // First vertex: use direction from first segment
      const dx = valid[1][0] - valid[0][0]
      const dy = valid[1][1] - valid[0][1]
      // Perpendicular: rotate 90 degrees clockwise
      nx = dy
      ny = -dx
    } else if (i === valid.length - 1) {
      // Last vertex: use direction from last segment
      const dx = valid[i][0] - valid[i - 1][0]
      const dy = valid[i][1] - valid[i - 1][1]
      nx = dy
      ny = -dx
    } else {
      // Interior vertex: average perpendiculars of adjacent segments (miter join)
      const dx1 = valid[i][0] - valid[i - 1][0]
      const dy1 = valid[i][1] - valid[i - 1][1]
      const dx2 = valid[i + 1][0] - valid[i][0]
      const dy2 = valid[i + 1][1] - valid[i][1]

      // Perpendicular of each segment
      const nx1 = dy1,
        ny1 = -dx1
      const nx2 = dy2,
        ny2 = -dx2

      // Average
      nx = nx1 + nx2
      ny = ny1 + ny2
    }

    // Normalize the perpendicular vector in meter-space
    const nxMeters = nx * metersPerDegLng
    const nyMeters = ny * METERS_PER_DEG_LAT
    const len = Math.sqrt(nxMeters * nxMeters + nyMeters * nyMeters)

    if (len === 0) {
      result.push([lng, lat])
      continue
    }

    // Scale to desired offset in meters, then convert back to degrees
    const scale = offsetMeters / len
    result.push([lng + nx * scale, lat + ny * scale])
  }

  return result
}

/**
 * Get the offset coordinates for a fiber based on its direction.
 * Uses precomputed coordinates if available, otherwise computes offset on-the-fly.
 *
 * This centralizes the logic that was previously duplicated across:
 * - FiberLayer, VehicleLayer3d, SpeedHeatmapLayer
 * - SectionLayer, SectionResizeHandles, ClickHandler
 * - LandmarkSelectionLayer
 */
export function getFiberOffsetCoords(
  fiber: Pick<FiberLine, 'coordinates' | 'direction' | 'coordsPrecomputed'>,
): [number, number][] {
  if (fiber.coordsPrecomputed) {
    // Coordinates already include directional offset from backend
    return filterValidCoords(fiber.coordinates as ([number, number] | [null, null])[])
  }
  // Compute offset: direction 0 = right (+), direction 1 = left (-)
  const offset = fiber.direction === 0 ? +DIRECTION_OFFSET_METERS : -DIRECTION_OFFSET_METERS
  return offsetCoordinates(fiber.coordinates as ([number, number] | [null, null])[], offset)
}
