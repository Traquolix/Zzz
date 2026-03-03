import { useEffect, useState, useCallback } from 'react'
import { useRealtime } from '@/hooks/useRealtime'
import { parseVehicleCount } from '@/lib/parseMessage'
import type { VehicleCount } from '@/types/realtime'

const COUNT_TTL_MS = 60_000 // Keep counts for 60s

/**
 * Hook to subscribe to AI-derived vehicle flow counts.
 *
 * Receives VehicleCount messages from the "counts" WebSocket channel
 * and maintains a map of the latest count per fiber section.
 * Stale entries (older than 60s) are evicted on each update.
 */
export function useVehicleCounts() {
    const { subscribe } = useRealtime()
    const [counts, setCounts] = useState<Map<string, VehicleCount>>(new Map())

    useEffect(() => {
        return subscribe('counts', (data: unknown) => {
            // Counts may arrive as a single object or an array
            const items = Array.isArray(data) ? data : [data]

            setCounts(prev => {
                const next = new Map(prev)
                const now = Date.now()

                for (const item of items) {
                    const count = parseVehicleCount(item)
                    if (!count) continue

                    const key = `${count.fiberLine}:${count.channelStart}-${count.channelEnd}`
                    next.set(key, count)
                }

                // Evict stale entries
                for (const [k, v] of next) {
                    if (now - v.timestamp > COUNT_TTL_MS) next.delete(k)
                }

                return next
            })
        })
    }, [subscribe])

    /** Get the latest count for a specific fiber section. */
    const getCount = useCallback(
        (fiberLine: string, channelStart: number, channelEnd: number): VehicleCount | null => {
            const key = `${fiberLine}:${channelStart}-${channelEnd}`
            return counts.get(key) ?? null
        },
        [counts],
    )

    /** Get total vehicle count across all sections. */
    const totalVehicles = useCallback((): number => {
        let total = 0
        for (const count of counts.values()) {
            total += count.vehicleCount
        }
        return Math.round(total)
    }, [counts])

    return { counts, getCount, totalVehicles }
}
