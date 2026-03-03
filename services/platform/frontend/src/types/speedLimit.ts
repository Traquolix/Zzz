import type { FiberRange } from './fiber'

export type SpeedLimitZone = FiberRange & {
    limit: number           // km/h
}

/**
 * Get the speed limit for a specific channel on a fiber.
 * Returns null if no zone covers this channel (falls back to absolute thresholds).
 */
export function getSpeedLimitForChannel(
    fiberId: string,
    channel: number,
    zones: Map<string, SpeedLimitZone>
): number | null {
    for (const zone of zones.values()) {
        if (zone.fiberId === fiberId &&
            channel >= zone.startChannel &&
            channel <= zone.endChannel) {
            return zone.limit
        }
    }
    return null
}

// Color conversion functions moved to @/lib/theme.ts:
//   speedToColorWithLimit() → theme.speedToColorWithLimit()
//   speedToRGBWithLimit()   → theme.speedToRGBWithLimit()
export { speedToColorWithLimit, speedToRGBWithLimit } from '@/lib/theme'
