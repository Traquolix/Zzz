import type { Fiber, Section, SpeedThresholds } from './types'
import type { CoverageRange } from '@/api/fibers'
import { getFiberOffsetCoords } from '@/lib/geoUtils'
import { COLORS } from '@/lib/theme'
import carrosJson from '../../../../../../infrastructure/clickhouse/cables/carros.json'
import mathisJson from '../../../../../../infrastructure/clickhouse/cables/mathis.json'
import promenadeJson from '../../../../../../infrastructure/clickhouse/cables/promenade.json'

// ── Map constants ──────────────────────────────────────────────────────────
export const MAP_CENTER: [number, number] = [7.24, 43.72]
export const MAP_ZOOM = 12

// ── Cable JSON typing ─────────────────────────────────────────────────────

interface CableJson {
  id: string
  name: string
  coordinates: ([number, number] | [null, null])[]
  color: string
  directional_paths?: Record<string, ([number, number] | [null, null])[]>
}

// ── Build fibers from cable JSONs (full per-channel coordinates) ──────────

const cableConfigs: { json: CableJson; colors: [string, string] }[] = [
  { json: carrosJson as unknown as CableJson, colors: [COLORS.fiber.default, COLORS.fiber.default] },
  { json: mathisJson as unknown as CableJson, colors: [COLORS.fiber.default, COLORS.fiber.default] },
  { json: promenadeJson as unknown as CableJson, colors: [COLORS.fiber.default, COLORS.fiber.default] },
]

function buildFibers(): Fiber[] {
  const result: Fiber[] = []
  for (const { json, colors } of cableConfigs) {
    for (const dir of [0, 1] as const) {
      const dp = json.directional_paths?.[String(dir)]
      const hasDirectional = dp != null && dp.length > 0
      result.push({
        id: `${json.id}:${dir}`,
        parentCableId: json.id,
        direction: dir,
        name: json.name.replace(/^Cable\s+/, ''),
        color: colors[dir],
        totalChannels: json.coordinates.length,
        coordinates: hasDirectional ? dp! : json.coordinates,
        coordsPrecomputed: hasDirectional,
      })
    }
  }
  return result
}

export const fibers: Fiber[] = buildFibers()

// Precompute offset coords (null-filtered) for rendering fiber lines.
// getFiberOffsetCoords handles nulls internally; cast bridges the Dashboard Fiber type.
export const fiberOffsetCache = new Map<string, [number, number][]>(
  fibers.map(f => [f.id, getFiberOffsetCoords({ ...f, coordinates: f.coordinates as [number, number][] })]),
)

// ── Simplified fiber coords for Mapbox line rendering ───────────────────
// Full-res coords (fiberOffsetCache) are kept for channel lookups, vehicle
// positioning, and section coords. Only the visual line layer uses simplified
// geometry so Mapbox redraws fewer vertices on every frame.

/**
 * Douglas-Peucker polyline simplification.
 * Removes points that deviate less than `tolerance` from the straight-line
 * segment between their neighbors. Preserves first and last points.
 */
function simplifyCoords(coords: [number, number][], tolerance: number): [number, number][] {
  if (coords.length <= 2) return coords

  let maxDist = 0
  let maxIdx = 0
  const [ax, ay] = coords[0]
  const [bx, by] = coords[coords.length - 1]
  const dx = bx - ax
  const dy = by - ay
  const lenSq = dx * dx + dy * dy

  for (let i = 1; i < coords.length - 1; i++) {
    const [px, py] = coords[i]
    let dist: number
    if (lenSq === 0) {
      dist = Math.sqrt((px - ax) ** 2 + (py - ay) ** 2)
    } else {
      const t = Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / lenSq))
      const projX = ax + t * dx
      const projY = ay + t * dy
      dist = Math.sqrt((px - projX) ** 2 + (py - projY) ** 2)
    }
    if (dist > maxDist) {
      maxDist = dist
      maxIdx = i
    }
  }

  if (maxDist <= tolerance) {
    return [coords[0], coords[coords.length - 1]]
  }

  const left = simplifyCoords(coords.slice(0, maxIdx + 1), tolerance)
  const right = simplifyCoords(coords.slice(maxIdx), tolerance)
  return [...left.slice(0, -1), ...right]
}

// ~0.5m tolerance in degrees — invisible even at zoom 17 (1px ≈ 1m), well within
// the line's rendered width, but eliminates collinear points on straight stretches.
const SIMPLIFY_TOLERANCE = 0.000005

/** Simplified fiber coords for Mapbox line rendering only. */
export const fiberRenderCache = new Map<string, [number, number][]>(
  fibers.map(f => {
    const full = fiberOffsetCache.get(f.id)!
    return [f.id, simplifyCoords(full, SIMPLIFY_TOLERANCE)]
  }),
)

/**
 * Build a render cache that contains only the data-covered portions of each fiber.
 * Returns Map<fiberId, segments[]> where each segment is a simplified coordinate array.
 * Disjoint coverage ranges produce separate segments (rendered as MultiLineString).
 */
export function buildCoverageRenderCache(coverageMap: Map<string, CoverageRange[]>): Map<string, [number, number][][]> {
  const cache = new Map<string, [number, number][][]>()
  for (const fiber of fibers) {
    const ranges = coverageMap.get(fiber.parentCableId)
    if (!ranges || ranges.length === 0) continue
    const segments: [number, number][][] = []
    for (const range of ranges) {
      const coords = getSectionCoords(fiber, range.start, range.end)
      if (coords.length >= 2) {
        segments.push(simplifyCoords(coords, SIMPLIFY_TOLERANCE))
      }
    }
    if (segments.length > 0) {
      cache.set(fiber.id, segments)
    }
  }
  return cache
}

// ── Helpers ─────────────────────────────────────────────────────────────

export const defaultSpeedThresholds: SpeedThresholds = { green: 80, yellow: 60, orange: 30 }

export function getSpeedColor(speed: number, thresholds?: SpeedThresholds): string {
  const t = thresholds ?? defaultSpeedThresholds
  if (speed >= t.green) return COLORS.speed.fast
  if (speed >= t.yellow) return COLORS.speed.normal
  if (speed >= t.orange) return COLORS.speed.slow
  return COLORS.speed.stopped
}

export function getSpeedColorRGBA(
  speed: number,
  opacity: number,
  thresholds?: SpeedThresholds,
): [number, number, number, number] {
  const a = Math.floor(opacity * 220)
  const t = thresholds ?? defaultSpeedThresholds
  if (speed >= t.green) return [...COLORS.speedRGB.fast, a]
  if (speed >= t.yellow) return [...COLORS.speedRGB.normal, a]
  if (speed >= t.orange) return [...COLORS.speedRGB.slow, a]
  return [...COLORS.speedRGB.stopped, a]
}

/** Build a lookup to find which section a (cableId, direction, channel) belongs to, returning its thresholds. */
export function buildThresholdLookup(
  sections: Section[],
  fiberThresholds: Record<string, SpeedThresholds>,
): (cableId: string, direction: 0 | 1, channel: number) => SpeedThresholds {
  type SectionRange = { start: number; end: number; thresholds: SpeedThresholds }
  const byCable = new Map<string, Map<number, { ranges: SectionRange[]; fallback: SpeedThresholds }>>()

  for (const sec of sections) {
    let byDir = byCable.get(sec.fiberId)
    if (!byDir) {
      byDir = new Map()
      byCable.set(sec.fiberId, byDir)
    }
    let entry = byDir.get(sec.direction)
    if (!entry) {
      const fid = findFiber(sec.fiberId, sec.direction)?.id ?? ''
      entry = { ranges: [], fallback: fiberThresholds[fid] ?? defaultSpeedThresholds }
      byDir.set(sec.direction, entry)
    }
    entry.ranges.push({ start: sec.startChannel, end: sec.endChannel, thresholds: sec.speedThresholds })
  }

  return (cableId: string, direction: 0 | 1, channel: number): SpeedThresholds => {
    const entry = byCable.get(cableId)?.get(direction)
    if (entry) {
      for (const s of entry.ranges) {
        if (channel >= s.start && channel <= s.end) return s.thresholds
      }
      return entry.fallback
    }
    return defaultSpeedThresholds
  }
}

// ── Channel → coordinate mapping ────────────────────────────────────────
// With full per-channel coordinates, channel IS the array index.
// For precomputed fibers (Carros), fiber.coordinates are already directional.
// For non-precomputed fibers (Mathis/Promenade), we look up the offset cache
// so dots render on the directional line, not the center-line.
// The offset cache is null-filtered (shorter), so we build a channel→index map.

const channelToOffsetIndex = new Map<string, Map<number, number>>()
// Reverse map: offset array index → real channel number.
// The offset cache is null-filtered (shorter than fiber.coordinates), so index ≠ channel.
// Used by findNearestFiberPoint to return the correct channel after snapping to offset coords.
export const offsetIndexToChannel = new Map<string, number[]>()
for (const fiber of fibers) {
  const forward = new Map<number, number>()
  const reverse: number[] = []
  let idx = 0
  for (let ch = 0; ch < fiber.coordinates.length; ch++) {
    const c = fiber.coordinates[ch]
    if (c[0] != null && c[1] != null) {
      forward.set(ch, idx)
      reverse.push(ch)
      idx++
    }
  }
  if (!fiber.coordsPrecomputed) {
    channelToOffsetIndex.set(fiber.id, forward)
  }
  offsetIndexToChannel.set(fiber.id, reverse)
}

const fiberIndex = new Map<string, Map<number, Fiber>>()
for (const f of fibers) {
  let byDir = fiberIndex.get(f.parentCableId)
  if (!byDir) {
    byDir = new Map()
    fiberIndex.set(f.parentCableId, byDir)
  }
  byDir.set(f.direction, f)
}

/** Find the directional fiber entry for a cable ID + direction. */
export function findFiber(cableId: string, direction: number): Fiber | undefined {
  return fiberIndex.get(cableId)?.get(direction)
}

/** Get the display color for a fiber, checking user overrides first. */
export function getFiberColor(fiber: Fiber, fiberColors: Record<string, string>): string {
  return fiberColors[fiber.id] ?? fiber.color
}

export function channelToCoord(fiber: Fiber, channel: number): [number, number] | null {
  if (channel < 0 || channel >= fiber.coordinates.length) return null

  if (fiber.coordsPrecomputed) {
    const c = fiber.coordinates[channel]
    if (c[0] == null || c[1] == null) return null
    return c as [number, number]
  }

  // Non-precomputed: use offset cache for directional placement
  const idxMap = channelToOffsetIndex.get(fiber.id)
  if (!idxMap) return null
  const offsetIdx = idxMap.get(channel)
  if (offsetIdx == null) return null
  const offsetCoords = fiberOffsetCache.get(fiber.id)
  if (!offsetCoords || offsetIdx >= offsetCoords.length) return null
  return offsetCoords[offsetIdx]
}

/** Return directional coordinates for a channel range on a fiber.
 *  For precomputed fibers (Carros), slices fiber.coordinates directly.
 *  For non-precomputed fibers (Mathis/Promenade), maps through the offset cache
 *  so the coords land on the directional line, not the center-line.
 */
export function getSectionCoords(fiber: Fiber, startChannel: number, endChannel: number): [number, number][] {
  if (fiber.coordsPrecomputed) {
    const slice = fiber.coordinates.slice(startChannel, endChannel + 1)
    return slice.filter(c => c[0] != null && c[1] != null) as [number, number][]
  }

  // Non-precomputed: map each channel to offset index, then look up offset coords
  const idxMap = channelToOffsetIndex.get(fiber.id)
  const offsetCoords = fiberOffsetCache.get(fiber.id)
  if (!idxMap || !offsetCoords) return []

  const result: [number, number][] = []
  for (let ch = startChannel; ch <= endChannel; ch++) {
    const idx = idxMap.get(ch)
    if (idx != null && idx < offsetCoords.length) {
      result.push(offsetCoords[idx])
    }
  }
  return result
}
