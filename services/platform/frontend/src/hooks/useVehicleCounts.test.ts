import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useVehicleCounts } from './useVehicleCounts'
import type { VehicleCount } from '@/types/realtime'

// Mock useRealtime hook
vi.mock('@/hooks/useRealtime', () => ({
    useRealtime: vi.fn(),
}))

// Mock parseVehicleCount from lib
vi.mock('@/lib/parseMessage', () => ({
    parseVehicleCount: vi.fn((data) => {
        // Simple passthrough validation
        if (
            data &&
            typeof data === 'object' &&
            'fiberLine' in data &&
            'channelStart' in data &&
            'channelEnd' in data &&
            'vehicleCount' in data &&
            'timestamp' in data
        ) {
            return data
        }
        return null
    }),
}))

import { useRealtime } from '@/hooks/useRealtime'

describe('useVehicleCounts', () => {
    let mockSubscribe: ReturnType<typeof vi.fn>
    let subscriberCallbacks: Map<string, (data: unknown) => void>

    beforeEach(() => {
        vi.clearAllMocks()
        subscriberCallbacks = new Map()

        mockSubscribe = vi.fn((channel: string, callback: (data: unknown) => void) => {
            subscriberCallbacks.set(channel, callback)
            // Return unsubscribe function
            return () => {
                subscriberCallbacks.delete(channel)
            }
        })

        vi.mocked(useRealtime).mockReturnValue({
            subscribe: mockSubscribe,
        } as any)
    })

    it('initializes with empty counts map', () => {
        const { result } = renderHook(() => useVehicleCounts())

        expect(result.current.counts.size).toBe(0)
        expect(result.current.getCount('fiber-1', 0, 10)).toBeNull()
        expect(result.current.totalVehicles()).toBe(0)
    })

    it('subscribes to counts channel on mount', () => {
        renderHook(() => useVehicleCounts())

        expect(mockSubscribe).toHaveBeenCalledWith(
            'counts',
            expect.any(Function),
        )
    })

    it('updates counts from single vehicle count message', () => {
        const { result } = renderHook(() => useVehicleCounts())

        const vehicleCount: VehicleCount = {
            fiberLine: 'fiber-1',
            channelStart: 0,
            channelEnd: 10,
            vehicleCount: 5,
            timestamp: Date.now(),
        }

        act(() => {
            const callback = subscriberCallbacks.get('counts')
            callback?.(vehicleCount)
        })

        expect(result.current.counts.size).toBe(1)
        const retrieved = result.current.getCount('fiber-1', 0, 10)
        expect(retrieved).toEqual(vehicleCount)
    })

    it('updates counts from array of vehicle count messages', () => {
        const { result } = renderHook(() => useVehicleCounts())

        const vehicleCounts: VehicleCount[] = [
            {
                fiberLine: 'fiber-1',
                channelStart: 0,
                channelEnd: 10,
                vehicleCount: 5,
                timestamp: Date.now(),
            },
            {
                fiberLine: 'fiber-2',
                channelStart: 0,
                channelEnd: 10,
                vehicleCount: 3,
                timestamp: Date.now(),
            },
        ]

        act(() => {
            const callback = subscriberCallbacks.get('counts')
            callback?.(vehicleCounts)
        })

        expect(result.current.counts.size).toBe(2)
        expect(result.current.getCount('fiber-1', 0, 10)?.vehicleCount).toBe(5)
        expect(result.current.getCount('fiber-2', 0, 10)?.vehicleCount).toBe(3)
    })

    it('getCount returns null for non-existent fiber', () => {
        const { result } = renderHook(() => useVehicleCounts())

        const vehicleCount: VehicleCount = {
            fiberLine: 'fiber-1',
            channelStart: 0,
            channelEnd: 10,
            vehicleCount: 5,
            timestamp: Date.now(),
        }

        act(() => {
            const callback = subscriberCallbacks.get('counts')
            callback?.(vehicleCount)
        })

        expect(result.current.getCount('fiber-999', 0, 10)).toBeNull()
    })

    it('calculates total vehicles correctly', () => {
        const { result } = renderHook(() => useVehicleCounts())

        const vehicleCounts: VehicleCount[] = [
            {
                fiberLine: 'fiber-1',
                channelStart: 0,
                channelEnd: 10,
                vehicleCount: 5,
                timestamp: Date.now(),
            },
            {
                fiberLine: 'fiber-2',
                channelStart: 0,
                channelEnd: 10,
                vehicleCount: 3,
                timestamp: Date.now(),
            },
            {
                fiberLine: 'fiber-3',
                channelStart: 0,
                channelEnd: 10,
                vehicleCount: 2,
                timestamp: Date.now(),
            },
        ]

        act(() => {
            const callback = subscriberCallbacks.get('counts')
            callback?.(vehicleCounts)
        })

        expect(result.current.totalVehicles()).toBe(10)
    })

    it('evicts stale entries older than TTL (60 seconds)', () => {
        vi.useFakeTimers()
        const { result } = renderHook(() => useVehicleCounts())

        const now = Date.now()
        const vehicleCounts: VehicleCount[] = [
            {
                fiberLine: 'fiber-1',
                channelStart: 0,
                channelEnd: 10,
                vehicleCount: 5,
                timestamp: now - 70_000, // 70 seconds old - should be evicted
            },
            {
                fiberLine: 'fiber-2',
                channelStart: 0,
                channelEnd: 10,
                vehicleCount: 3,
                timestamp: now - 30_000, // 30 seconds old - should be kept
            },
        ]

        act(() => {
            const callback = subscriberCallbacks.get('counts')
            callback?.(vehicleCounts)
        })

        // The old entry should be evicted, only the newer one remains
        expect(result.current.counts.size).toBe(1)
        expect(result.current.getCount('fiber-1', 0, 10)).toBeNull()
        expect(result.current.getCount('fiber-2', 0, 10)).not.toBeNull()

        vi.useRealTimers()
    })

    it('updates count when same fiber receives new message', () => {
        const { result } = renderHook(() => useVehicleCounts())

        const now = Date.now()
        const vehicleCount1: VehicleCount = {
            fiberLine: 'fiber-1',
            channelStart: 0,
            channelEnd: 10,
            vehicleCount: 5,
            timestamp: now,
        }

        act(() => {
            const callback = subscriberCallbacks.get('counts')
            callback?.(vehicleCount1)
        })

        expect(result.current.getCount('fiber-1', 0, 10)?.vehicleCount).toBe(5)

        const vehicleCount2: VehicleCount = {
            fiberLine: 'fiber-1',
            channelStart: 0,
            channelEnd: 10,
            vehicleCount: 8,
            timestamp: now + 1000,
        }

        act(() => {
            const callback = subscriberCallbacks.get('counts')
            callback?.(vehicleCount2)
        })

        expect(result.current.counts.size).toBe(1)
        expect(result.current.getCount('fiber-1', 0, 10)?.vehicleCount).toBe(8)
    })

    it('handles invalid count messages gracefully', () => {
        const { result } = renderHook(() => useVehicleCounts())

        // Invalid message (missing required fields)
        const invalidData = {
            fiberLine: 'fiber-1',
            // Missing other required fields
        }

        act(() => {
            const callback = subscriberCallbacks.get('counts')
            callback?.(invalidData)
        })

        // Should remain empty since the message was invalid
        expect(result.current.counts.size).toBe(0)
    })
})
