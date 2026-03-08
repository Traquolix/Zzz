import type { Car, SimConfig } from './types'

/**
 * Generate a UUID v4.
 * Uses crypto.randomUUID() in secure contexts (HTTPS),
 * falls back to Math.random() for HTTP deployments.
 */
export function generateUUID(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  // Fallback for non-secure contexts (HTTP)
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => {
    const r = (Math.random() * 16) | 0
    const v = c === 'x' ? r : (r & 0x3) | 0x8
    return v.toString(16)
  })
}

export function speedToChannelsPerMs(speedKmh: number, metersPerChannel: number): number {
  return (speedKmh * 1000) / 3600 / 1000 / metersPerChannel
}

export function randomOffset(segmentWidth: number): number {
  return (Math.random() - 0.5) * segmentWidth
}

export function lanesForDirection(direction: 0 | 1): number[] {
  return direction === 0 ? [0, 1, 2, 3, 4] : [5, 6, 7, 8, 9]
}

export function createCars(count: number, direction: 0 | 1, config: SimConfig): Car[] {
  return lanesForDirection(direction)
    .slice(0, count)
    .map(lane => ({
      id: generateUUID(),
      lane,
      offset: randomOffset(config.segmentWidth),
      opacity: 1,
      state: 'active' as const,
    }))
}
