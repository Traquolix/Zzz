/**
 * Runtime type guards for WebSocket and REST message data.
 *
 * All array parsers use createArrayParser() which provides:
 * - Type guard validation per item
 * - Drop metrics tracking per channel
 * - Console warnings on invalid items (first 3 shown for debugging)
 * - Graceful handling of non-array input (returns [])
 */
import type { Detection } from '@/types/realtime'
import type { Incident } from '@/types/incident'
import type { FrequencyReading } from '@/types/infrastructure'
import { logger } from '@/lib/logger'

// --- Drop tracking for observability ---
const _dropCounts: Record<string, number> = {}
const _totalReceived: Record<string, number> = {}

function _ensureChannel(channel: string): void {
  if (!(channel in _dropCounts)) {
    _dropCounts[channel] = 0
    _totalReceived[channel] = 0
  }
}

// --- Type guards ---

function isObject(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null && !Array.isArray(v)
}

function isDetection(d: unknown): d is Detection {
  if (
    !(
      isObject(d) &&
      typeof d.fiberId === 'string' &&
      typeof d.direction === 'number' &&
      typeof d.channel === 'number' &&
      typeof d.speed === 'number' &&
      typeof d.count === 'number' &&
      typeof d.nCars === 'number' &&
      typeof d.timestamp === 'number'
    )
  )
    return false
  // Default fields that may be absent during rolling deploys
  const rec = d as Record<string, unknown>
  if (typeof rec.nTrucks !== 'number') rec.nTrucks = 0
  if (typeof rec.glrtMax !== 'number') rec.glrtMax = 0
  if (typeof rec.strainPeak !== 'number') rec.strainPeak = 0
  if (typeof rec.strainRms !== 'number') rec.strainRms = 0
  return true
}

function isIncident(d: unknown): d is Incident {
  return (
    isObject(d) &&
    typeof d.id === 'string' &&
    typeof d.type === 'string' &&
    Array.isArray(d.tags) &&
    typeof d.fiberId === 'string' &&
    typeof d.direction === 'number' &&
    typeof d.channel === 'number' &&
    typeof d.detectedAt === 'string' &&
    typeof d.status === 'string'
  )
}

function isFrequencyReading(d: unknown): d is FrequencyReading {
  return (
    isObject(d) &&
    typeof d.infrastructureId === 'string' &&
    typeof d.frequency === 'number' &&
    typeof d.amplitude === 'number' &&
    typeof d.timestamp === 'number'
  )
}

// --- Generic array parser factory ---

/**
 * Creates a type-safe array parser with drop tracking.
 *
 * The returned function accepts unknown data, validates each item against
 * the provided type guard, tracks drops per channel, and returns only
 * valid items. Non-array input returns [] with a console warning.
 */
function createArrayParser<T>(channel: string, guard: (item: unknown) => item is T): (data: unknown) => T[] {
  _ensureChannel(channel)

  return (data: unknown): T[] => {
    if (!Array.isArray(data)) {
      if (data !== undefined && data !== null) {
        logger.warn(`[${channel}] Expected array, got:`, typeof data, data)
      }
      return []
    }

    const valid: T[] = []
    const invalid: unknown[] = []

    for (const item of data) {
      if (guard(item)) {
        valid.push(item)
      } else {
        invalid.push(item)
      }
    }

    _totalReceived[channel] += data.length
    if (invalid.length > 0) {
      _dropCounts[channel] += invalid.length
      logger.warn(`[${channel}] Dropped ${invalid.length}/${data.length} invalid items:`, invalid.slice(0, 3))
    }

    return valid
  }
}

// --- Exported array parsers ---

export const parseDetections = createArrayParser<Detection>('detections', isDetection)
export const parseIncidents = createArrayParser<Incident>('incidents', isIncident)
export const parseFrequencyReadings = createArrayParser<FrequencyReading>('frequencyReadings', isFrequencyReading)

// --- Single-item parsers (for WebSocket messages arriving as individual objects) ---

/** Parse a single Incident from unknown data. Returns null if invalid. */
export function parseIncident(data: unknown): Incident | null {
  return isIncident(data) ? data : null
}
