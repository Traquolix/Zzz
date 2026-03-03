/**
 * Integration tests for useSectionStats hook.
 *
 * Uses renderHook with mocked useRealtime and useVehicleCounts to verify
 * subscription lifecycle, cancelled flag, batching, and stats computation.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import type { FiberSection } from '@/types/section'

// Track subscribe/unsubscribe calls
let subscribeCallbacks: Record<string, (data: unknown) => void> = {}
let unsubscribeFns: Record<string, ReturnType<typeof vi.fn>> = {}
const mockAiCounts = new Map()

vi.mock('@/hooks/useRealtime', () => ({
    useRealtime: () => ({
        subscribe: vi.fn((channel: string, cb: (data: unknown) => void) => {
            subscribeCallbacks[channel] = cb
            const unsub = vi.fn()
            unsubscribeFns[channel] = unsub
            return unsub
        }),
    }),
}))

vi.mock('@/hooks/useVehicleCounts', () => ({
    useVehicleCounts: () => ({
        counts: mockAiCounts,
    }),
}))

// Import after mocks
import { useSectionStats } from './useSectionStats'

// Stable reference — created once, reused across renders to avoid infinite re-render
const SECTIONS: Map<string, FiberSection> = new Map([
    ['sec-1', {
        id: 'sec-1',
        fiberId: 'carros:0',
        startChannel: 100,
        endChannel: 200,
        name: 'Test Section',
    }],
])

describe('useSectionStats hook', () => {
    beforeEach(() => {
        vi.useFakeTimers()
        subscribeCallbacks = {}
        unsubscribeFns = {}
        mockAiCounts.clear()
    })

    afterEach(() => {
        vi.useRealTimers()
    })

    it('subscribes to detections on mount', () => {
        renderHook(() => useSectionStats(SECTIONS))
        expect(subscribeCallbacks['detections']).toBeDefined()
    })

    it('unsubscribes on unmount', () => {
        const { unmount } = renderHook(() => useSectionStats(SECTIONS))
        unmount()
        expect(unsubscribeFns['detections']).toHaveBeenCalled()
    })

    it('computes stats from detection batch after flush interval', () => {
        const { result } = renderHook(() => useSectionStats(SECTIONS))

        act(() => {
            subscribeCallbacks['detections']([
                { fiberLine: 'carros:0', channel: 150, speed: 80, count: 1, direction: 0, timestamp: Date.now() },
                { fiberLine: 'carros:0', channel: 160, speed: 100, count: 1, direction: 0, timestamp: Date.now() },
            ])
        })

        // Stats not yet updated — still in buffer
        expect(result.current.stats.get('sec-1')!.direction0.avgSpeed).toBeNull()

        // Advance past flush interval (500ms)
        act(() => {
            vi.advanceTimersByTime(600)
        })

        const stats = result.current.stats.get('sec-1')
        expect(stats).toBeDefined()
        expect(stats!.direction0.avgSpeed).toBe(90) // (80+100)/2
        expect(stats!.direction0.vehicleCount).toBe(2)
    })

    it('initializes with zero stats for all sections', () => {
        const { result } = renderHook(() => useSectionStats(SECTIONS))
        const stats = result.current.stats.get('sec-1')
        expect(stats).toBeDefined()
        expect(stats!.distance).toBe(500) // (200-100) * 5
        expect(stats!.combined.vehicleCount).toBe(0)
        expect(stats!.combined.avgSpeed).toBeNull()
    })

    it('overrides vehicleCount with AI count when available', () => {
        mockAiCounts.set('ai-1', {
            fiberLine: 'carros',
            channelStart: 100,
            channelEnd: 200,
            vehicleCount: 42,
            timestamp: Date.now(),
        })

        const { result } = renderHook(() => useSectionStats(SECTIONS))

        act(() => {
            subscribeCallbacks['detections']([
                { fiberLine: 'carros:0', channel: 150, speed: 80, count: 1, direction: 0, timestamp: Date.now() },
            ])
        })

        // Advance past flush interval
        act(() => {
            vi.advanceTimersByTime(600)
        })

        const stats = result.current.stats.get('sec-1')
        // combined.vehicleCount should be overridden by AI count
        expect(stats!.combined.vehicleCount).toBe(42)
    })

    it('batches multiple detection pushes into single state update', () => {
        const { result } = renderHook(() => useSectionStats(SECTIONS))

        // Push 3 batches rapidly (within 500ms window)
        act(() => {
            subscribeCallbacks['detections']([
                { fiberLine: 'carros:0', channel: 150, speed: 60, count: 1, direction: 0, timestamp: Date.now() },
            ])
            subscribeCallbacks['detections']([
                { fiberLine: 'carros:0', channel: 160, speed: 80, count: 1, direction: 0, timestamp: Date.now() },
            ])
            subscribeCallbacks['detections']([
                { fiberLine: 'carros:0', channel: 170, speed: 100, count: 1, direction: 0, timestamp: Date.now() },
            ])
        })

        // Single flush processes all 3 batches
        act(() => {
            vi.advanceTimersByTime(600)
        })

        const stats = result.current.stats.get('sec-1')
        expect(stats!.direction0.avgSpeed).toBe(80) // (60+80+100)/3
        expect(stats!.direction0.vehicleCount).toBe(3)
    })
})
