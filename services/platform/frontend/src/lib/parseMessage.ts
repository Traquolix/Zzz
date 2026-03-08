/**
 * Runtime type guards for WebSocket and REST message data.
 *
 * All array parsers use createArrayParser() which provides:
 * - Type guard validation per item
 * - Drop metrics tracking per channel
 * - Console warnings on invalid items (first 3 shown for debugging)
 * - Graceful handling of non-array input (returns [])
 */
import type { Detection, VehicleCount } from '@/types/realtime'
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
  return (
    isObject(d) &&
    typeof d.fiberId === 'string' &&
    typeof d.direction === 'number' &&
    typeof d.channel === 'number' &&
    typeof d.speed === 'number' &&
    typeof d.count === 'number' &&
    typeof d.nCars === 'number' &&
    typeof d.nTrucks === 'number' &&
    typeof d.timestamp === 'number'
  )
}

function isVehicleCount(d: unknown): d is VehicleCount {
  return (
    isObject(d) &&
    typeof d.fiberId === 'string' &&
    typeof d.direction === 'number' &&
    typeof d.channelStart === 'number' &&
    typeof d.channelEnd === 'number' &&
    typeof d.vehicleCount === 'number' &&
    typeof d.timestamp === 'number'
  )
}

function isIncident(d: unknown): d is Incident {
  return (
    isObject(d) &&
    typeof d.id === 'string' &&
    typeof d.type === 'string' &&
    typeof d.severity === 'string' &&
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
export const parseVehicleCounts = createArrayParser<VehicleCount>('vehicleCounts', isVehicleCount)
export const parseIncidents = createArrayParser<Incident>('incidents', isIncident)
export const parseFrequencyReadings = createArrayParser<FrequencyReading>('frequencyReadings', isFrequencyReading)

// --- Single-item parsers (for WebSocket messages arriving as individual objects) ---

/** Parse a single VehicleCount from unknown data. Returns null if invalid. */
export function parseVehicleCount(data: unknown): VehicleCount | null {
  return isVehicleCount(data) ? data : null
}

/** Parse a single Incident from unknown data. Returns null if invalid. */
export function parseIncident(data: unknown): Incident | null {
  return isIncident(data) ? data : null
}
