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

/** Build a lookup to find which section a (fiberId, channel) belongs to, returning its thresholds. */
export function buildThresholdLookup(
  sections: Section[],
  fiberThresholds: Record<string, SpeedThresholds>,
): (fiberId: string, channel: number) => SpeedThresholds {
  // Sort sections by fiberId for grouped lookup
  const byFiber = new Map<string, { start: number; end: number; thresholds: SpeedThresholds }[]>()
  for (const sec of sections) {
    let list = byFiber.get(sec.fiberId)
    if (!list) {
      list = []
      byFiber.set(sec.fiberId, list)
    }
    list.push({ start: sec.startChannel, end: sec.endChannel, thresholds: sec.speedThresholds })
  }

  return (fiberId: string, channel: number): SpeedThresholds => {
    const list = byFiber.get(fiberId)
    if (list) {
      for (const s of list) {
        if (channel >= s.start && channel <= s.end) return s.thresholds
      }
    }
    return fiberThresholds[fiberId] ?? defaultSpeedThresholds
  }
}

// ── Channel → coordinate mapping ────────────────────────────────────────
// With full per-channel coordinates, channel IS the array index.
// For precomputed fibers (Carros), fiber.coordinates are already directional.
// For non-precomputed fibers (Mathis/Promenade), we look up the offset cache
// so dots render on the directional line, not the center-line.
// The offset cache is null-filtered (shorter), so we build a channel→index map.

const channelToOffsetIndex = new Map<string, Map<number, number>>()
for (const fiber of fibers) {
  if (!fiber.coordsPrecomputed) {
    const map = new Map<number, number>()
    let idx = 0
    for (let ch = 0; ch < fiber.coordinates.length; ch++) {
      const c = fiber.coordinates[ch]
      if (c[0] != null && c[1] != null) {
        map.set(ch, idx)
        idx++
      }
    }
    channelToOffsetIndex.set(fiber.id, map)
  }
}

export function channelToCoord(fiberLine: string, channel: number): [number, number] | null {
  const fiber = fibers.find(f => f.id === fiberLine)
  if (!fiber) return null
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
export function getSectionCoords(fiberId: string, startChannel: number, endChannel: number): [number, number][] {
  const fiber = fibers.find(f => f.id === fiberId)
  if (!fiber) return []

  if (fiber.coordsPrecomputed) {
    const slice = fiber.coordinates.slice(startChannel, endChannel + 1)
    return slice.filter(c => c[0] != null && c[1] != null) as [number, number][]
  }

  // Non-precomputed: map each channel to offset index, then look up offset coords
  const idxMap = channelToOffsetIndex.get(fiberId)
  const offsetCoords = fiberOffsetCache.get(fiberId)
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
  flow: { label: 'Flow', unit: 'veh/min', color: '#8b5cf6' },
  occupancy: { label: 'Occupancy', unit: '%', color: '#0ea5e9' },
}

/** Resolve a cable-level fiberId (e.g. "carros") to a directional fiber ID (e.g. "carros:0"). */
export function resolveDirectionalFiber(cableFiberId: string): string {
  // If already directional, return as-is
  if (cableFiberId.includes(':')) return cableFiberId
  return `${cableFiberId}:0`
}
