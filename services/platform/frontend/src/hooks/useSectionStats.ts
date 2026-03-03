import { useEffect, useState, useCallback, useRef } from 'react'
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
const FLUSH_INTERVAL_MS = 500 // ~2Hz state updates
const MAX_PENDING_DETECTIONS = 5000 // Safety cap on batch buffer between flushes

/**
 * Extract parent fiber ID from directional ID.
 * "mathis:0" -> "mathis", "carros:1" -> "carros"
 */
function getParentFiberId(directionalId: string): string {
    const colonIndex = directionalId.lastIndexOf(':')
    if (colonIndex === -1) return directionalId
    const suffix = directionalId.slice(colonIndex + 1)
    if (suffix === '0' || suffix === '1') {
        return directionalId.slice(0, colonIndex)
    }
    return directionalId
}

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

    const sectionParentId = getParentFiberId(section.fiberId)

    for (const count of counts.values()) {
        if (count.fiberLine !== sectionParentId) continue

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
 *
 * Performance: Batches incoming 10Hz detections in a ref and flushes to React
 * state at ~2Hz (500ms intervals). Only recomputes sections that received new
 * detections in the batch. Reads aiCounts via ref to avoid effect re-subscribe.
 */
export function useSectionStats(sections: Map<string, FiberSection>) {
    const { subscribe } = useRealtime()
    const { counts: aiCounts } = useVehicleCounts()
    const [stats, setStats] = useState<Map<string, SectionStats>>(() => {
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

    // Refs for batching — avoids effect dep on mutable data
    const pendingRef = useRef<Detection[]>([])
    const timerRef = useRef<number | null>(null)
    const aiCountsRef = useRef(aiCounts)
    const sectionsRef = useRef(sections)

    // Keep refs current without triggering re-subscribe
    useEffect(() => { aiCountsRef.current = aiCounts }, [aiCounts])
    useEffect(() => { sectionsRef.current = sections }, [sections])

    // Flush: recompute only sections that have new detections
    const flush = useCallback(() => {
        timerRef.current = null
        const batch = pendingRef.current
        pendingRef.current = []
        if (batch.length === 0) return

        // Index by fiberLine for O(1) lookup per section
        const byFiber = new Map<string, Detection[]>()
        for (const d of batch) {
            let arr = byFiber.get(d.fiberLine)
            if (!arr) {
                arr = []
                byFiber.set(d.fiberLine, arr)
            }
            arr.push(d)
        }

        const currentSections = sectionsRef.current
        const currentAiCounts = aiCountsRef.current

        setStats(prev => {
            const result = new Map(prev) // shallow copy — unaffected sections keep identity
            for (const [sectionId, section] of currentSections) {
                const fiberDetections = byFiber.get(section.fiberId)
                if (!fiberDetections) continue // skip unaffected sections

                const distance = Math.abs(section.endChannel - section.startChannel) * METERS_PER_CHANNEL

                // Filter to channels within this section
                const sectionDetections = fiberDetections.filter(d =>
                    d.channel >= section.startChannel &&
                    d.channel <= section.endChannel
                )

                if (sectionDetections.length === 0) continue

                const direction0 = computeDirectionStats(sectionDetections, distance, 0)
                const direction1 = computeDirectionStats(sectionDetections, distance, 1)
                const combined = computeDirectionStats(sectionDetections, distance, 'all')

                const aiCount = findMatchingCount(section, currentAiCounts)
                if (aiCount) {
                    combined.vehicleCount = Math.round(aiCount.vehicleCount)
                }

                result.set(sectionId, { distance, direction0, direction1, combined })
            }
            return result
        })
    }, [])

    // Subscribe to detections — push to buffer, schedule flush at 500ms
    // Deps: [subscribe] only — no aiCounts or sections causing re-subscribe
    useEffect(() => {
        const unsubscribe = subscribe('detections', (data: unknown) => {
            const detections = parseDetections(data)
            if (detections.length === 0) return

            pendingRef.current.push(...detections)

            // Hard cap: if flush is delayed, drop oldest to prevent memory spike
            if (pendingRef.current.length > MAX_PENDING_DETECTIONS) {
                pendingRef.current = pendingRef.current.slice(-MAX_PENDING_DETECTIONS)
            }

            if (timerRef.current === null) {
                timerRef.current = window.setTimeout(flush, FLUSH_INTERVAL_MS)
            }
        })

        return () => {
            unsubscribe()
            if (timerRef.current !== null) {
                clearTimeout(timerRef.current)
                timerRef.current = null
            }
            pendingRef.current = []
        }
    }, [subscribe, flush])

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
