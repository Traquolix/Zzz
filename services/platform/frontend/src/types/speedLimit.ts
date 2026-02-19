export type SpeedLimitZone = {
    id: string              // `zone:${fiberId}:${start}-${end}`
    fiberId: string
    startChannel: number
    endChannel: number
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

/**
 * Convert speed to color based on percentage of speed limit.
 * If no limit provided, uses absolute thresholds.
 */
export function speedToColorWithLimit(speed: number, limit: number | null): string {
    if (limit && limit > 0) {
        const pct = speed / limit
        if (pct >= 0.8) return '#22c55e'  // green - flowing well
        if (pct >= 0.6) return '#84cc16'  // lime
        if (pct >= 0.4) return '#eab308'  // yellow - slowing
        if (pct >= 0.2) return '#f97316'  // orange - congested
        return '#ef4444'                   // red - severe
    }
    // Fallback: absolute thresholds (original behavior)
    if (speed >= 80) return '#22c55e'
    if (speed >= 60) return '#84cc16'
    if (speed >= 40) return '#eab308'
    if (speed >= 20) return '#f97316'
    return '#ef4444'
}

/**
 * RGB version for deck.gl layers
 */
export function speedToRGBWithLimit(speed: number, limit: number | null): [number, number, number] {
    if (limit && limit > 0) {
        const pct = speed / limit
        if (pct >= 0.8) return [34, 197, 94]   // green
        if (pct >= 0.6) return [132, 204, 22]  // lime
        if (pct >= 0.4) return [234, 179, 8]   // yellow
        if (pct >= 0.2) return [249, 115, 22]  // orange
        return [239, 68, 68]                    // red
    }
    // Fallback
    if (speed >= 80) return [34, 197, 94]
    if (speed >= 60) return [132, 204, 22]
    if (speed >= 40) return [234, 179, 8]
    if (speed >= 20) return [249, 115, 22]
    return [239, 68, 68]
}
