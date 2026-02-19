import { useEffect, useState, useCallback } from 'react'
import { useRealtime } from '@/hooks/useRealtime'
import { useVehicleCounts } from '@/hooks/useVehicleCounts'
import type { FiberSection } from '@/types/section'
import { parseDetections } from '@/lib/parseMessage'
import type { Detection, VehicleCount } from '@/types/realtime'

export type DirectionStats = {
    avgSpeed: number | null // km/h
    travelTime: number | null // seconds
    vehicleCount: number
}

export type SectionStats = {
    distance: number // meters
    direction0: DirectionStats // -> direction
    direction1: DirectionStats // <- direction
    combined: DirectionStats // both directions
}

const METERS_PER_CHANNEL = 5

function computeDirectionStats(
    detections: Detection[],
    distance: number,
    directionFilter: 0 | 1 | 'all'
): DirectionStats {
    const filtered = directionFilter === 'all'
        ? detections
        : detections.filter(d => d.direction === directionFilter)

    if (filtered.length === 0) {
        return { avgSpeed: null, travelTime: null, vehicleCount: 0 }
    }

    let totalSpeed = 0
    let totalCount = 0
    for (const d of filtered) {
        totalSpeed += d.speed * d.count
        totalCount += d.count
    }

    const avgSpeed = totalCount > 0 ? totalSpeed / totalCount : null
    const travelTime = avgSpeed && avgSpeed > 0
        ? distance / (avgSpeed * 1000 / 3600)
        : null

    return { avgSpeed, travelTime, vehicleCount: totalCount }
}

/**
 * Find the best matching AI count for a section.
 * An AI count matches if it covers the same fiber and overlaps the section's channel range.
 */
function findMatchingCount(
    section: FiberSection,
    counts: Map<string, VehicleCount>,
): VehicleCount | null {
    let bestMatch: VehicleCount | null = null
    let bestOverlap = 0

    for (const count of counts.values()) {
        if (count.fiberLine !== section.fiberId) continue

        // Check overlap between section [startChannel, endChannel] and count [channelStart, channelEnd]
        const overlapStart = Math.max(section.startChannel, count.channelStart)
        const overlapEnd = Math.min(section.endChannel, count.channelEnd)
        const overlap = overlapEnd - overlapStart

        if (overlap > bestOverlap) {
            bestOverlap = overlap
            bestMatch = count
        }
    }

    return bestMatch
}

/**
 * Hook to compute real-time statistics for fiber sections.
 * Subscribes to raw detection events and computes instantaneous stats per section.
 * Each detection batch updates the stats immediately with current snapshot.
 * Stats are computed separately for each direction and combined.
 *
 * When AI-derived vehicle counts are available, they override the detection-based
 * vehicle count (which is just grouped channel hits, not calibrated flow).
 */
export function useSectionStats(sections: Map<string, FiberSection>) {
    const { subscribe } = useRealtime()
    const { counts: aiCounts } = useVehicleCounts()
    const [stats, setStats] = useState<Map<string, SectionStats>>(() => {
        // Initialize with empty stats for all sections
        const initial = new Map<string, SectionStats>()
        for (const [sectionId, section] of sections) {
            const distance = Math.abs(section.endChannel - section.startChannel) * METERS_PER_CHANNEL
            initial.set(sectionId, {
                distance,
                direction0: { avgSpeed: null, travelTime: null, vehicleCount: 0 },
                direction1: { avgSpeed: null, travelTime: null, vehicleCount: 0 },
                combined: { avgSpeed: null, travelTime: null, vehicleCount: 0 }
            })
        }
        return initial
    })

    // Subscribe to detections and compute instantaneous stats
    useEffect(() => {
        const unsubscribe = subscribe('detections', (data: unknown) => {
            const detections = parseDetections(data)
            if (detections.length === 0) return

            const result = new Map<string, SectionStats>()

            for (const [sectionId, section] of sections) {
                const distance = Math.abs(section.endChannel - section.startChannel) * METERS_PER_CHANNEL

                // Filter detections to this section
                const sectionDetections = detections.filter(d =>
                    d.fiberLine === section.fiberId &&
                    d.channel >= section.startChannel &&
                    d.channel <= section.endChannel
                )

                const direction0 = computeDirectionStats(sectionDetections, distance, 0)
                const direction1 = computeDirectionStats(sectionDetections, distance, 1)
                const combined = computeDirectionStats(sectionDetections, distance, 'all')

                // Override vehicleCount with AI-derived count if available
                const aiCount = findMatchingCount(section, aiCounts)
                if (aiCount) {
                    combined.vehicleCount = Math.round(aiCount.vehicleCount)
                }

                result.set(sectionId, { distance, direction0, direction1, combined })
            }

            setStats(result)
        })

        return unsubscribe
    }, [subscribe, sections, aiCounts])

    // Update distances when sections change
    useEffect(() => {
        setStats(prev => {
            const updated = new Map<string, SectionStats>()
            for (const [sectionId, section] of sections) {
                const distance = Math.abs(section.endChannel - section.startChannel) * METERS_PER_CHANNEL
                const existing = prev.get(sectionId)
                updated.set(sectionId, {
                    distance,
                    direction0: existing?.direction0 ?? { avgSpeed: null, travelTime: null, vehicleCount: 0 },
                    direction1: existing?.direction1 ?? { avgSpeed: null, travelTime: null, vehicleCount: 0 },
                    combined: existing?.combined ?? { avgSpeed: null, travelTime: null, vehicleCount: 0 }
                })
            }
            return updated
        })
    }, [sections])

    const getStats = useCallback((sectionId: string): SectionStats | null => {
        return stats.get(sectionId) ?? null
    }, [stats])

    return { stats, getStats }
}
