import type { Fiber, Section, IncidentType, SpeedThresholds } from './types'
import { getFiberOffsetCoords } from '@/lib/geoUtils'
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
  { json: carrosJson as unknown as CableJson, colors: ['#94a3b8', '#94a3b8'] },
  { json: mathisJson as unknown as CableJson, colors: ['#94a3b8', '#94a3b8'] },
  { json: promenadeJson as unknown as CableJson, colors: ['#94a3b8', '#94a3b8'] },
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
// getFiberOffsetCoords handles nulls internally; cast bridges the Prototype Fiber type.
export const fiberOffsetCache = new Map<string, [number, number][]>(
  fibers.map(f => [f.id, getFiberOffsetCoords({ ...f, coordinates: f.coordinates as [number, number][] })]),
)

// ── Helpers ─────────────────────────────────────────────────────────────

export const defaultSpeedThresholds: SpeedThresholds = { green: 80, yellow: 60, orange: 30 }
export const citySpeedThresholds: SpeedThresholds = { green: 45, yellow: 30, orange: 15 }

export function getSpeedColor(speed: number, thresholds?: SpeedThresholds): string {
  const t = thresholds ?? defaultSpeedThresholds
  if (speed >= t.green) return '#22c55e'
  if (speed >= t.yellow) return '#eab308'
  if (speed >= t.orange) return '#f97316'
  return '#ef4444'
}

export function getSpeedColorRGBA(
  speed: number,
  opacity: number,
  thresholds?: SpeedThresholds,
): [number, number, number, number] {
  const a = Math.floor(opacity * 220)
  const t = thresholds ?? defaultSpeedThresholds
  if (speed >= t.green) return [34, 197, 94, a] // green
  if (speed >= t.yellow) return [234, 179, 8, a] // yellow
  if (speed >= t.orange) return [249, 115, 22, a] // orange
  return [239, 68, 68, a] // red
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

// ── Severity / style constants ──────────────────────────────────────────

export const severityColor: Record<string, string> = {
  critical: '#ef4444',
  high: '#f97316',
  medium: '#f59e0b',
  low: '#22c55e',
}

export const incidentTypeIcon: Record<IncidentType, string> = {
  accident: '!',
  congestion: '\u25CF',
  slowdown: '\u25BC',
  anomaly: '?',
}

export const chartColors = {
  speed: { label: 'Speed', unit: 'km/h', color: '#6366f1' },
  flow: { label: 'Flow', unit: 'veh/h', color: '#8b5cf6' },
  occupancy: { label: 'Occupancy', unit: '%', color: '#0ea5e9' },
}
