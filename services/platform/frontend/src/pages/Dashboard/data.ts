import type { Fiber, Section, SpeedThresholds } from './types'
import { COLORS } from '@/lib/theme'

// ── Map constants ──────────────────────────────────────────────────────────
export const MAP_CENTER: [number, number] = [7.24, 43.72]
export const MAP_ZOOM = 12

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
  findFiber: (cableId: string, direction: number) => Fiber | undefined,
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

/** Get the display color for a fiber, checking user overrides first. */
export function getFiberColor(fiber: Fiber, fiberColors: Record<string, string>): string {
  return fiberColors[fiber.id] ?? fiber.color
}
