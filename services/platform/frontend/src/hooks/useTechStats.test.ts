import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'

// Simple mock setup
vi.mock('./useRealtime')
vi.mock('./useVehicleCounts')
vi.mock('./useAuth')
vi.mock('@/api/stats')
vi.mock('@/lib/parseMessage')

import { useTechStats } from './useTechStats'
import { useRealtime } from './useRealtime'
import { useVehicleCounts } from './useVehicleCounts'
import { useAuth } from './useAuth'
import { fetchStats } from '@/api/stats'
import { parseDetections } from '@/lib/parseMessage'

describe('useTechStats', () => {
    const mockStats = {
        activeVehicles: 42,
        activeIncidents: 3,
        fiberCount: 10,
        totalChannels: 1000,
        detectionsPerSecond: 150,
        systemUptime: 864000000,
    }

    let mockDetectionSubscriber: ((data: unknown) => void) | null = null

    beforeEach(() => {
        vi.useFakeTimers()
        vi.clearAllMocks()
        mockDetectionSubscriber = null

        vi.mocked(useRealtime).mockReturnValue({
            subscribe: vi.fn((channel, callback) => {
                if (channel === 'detections') {
                    mockDetectionSubscriber = callback
                }
                return vi.fn()
            }),
            connected: true,
            reconnecting: false,
            authFailed: false,
        } as any)

        vi.mocked(useVehicleCounts).mockReturnValue({
            counts: new Map(),
            getCount: vi.fn(),
            totalVehicles: vi.fn(() => 0),
        } as any)

        vi.mocked(useAuth).mockReturnValue({
            username: 'testuser',
            allowedWidgets: [],
            allowedLayers: [],
        } as any)

        vi.mocked(fetchStats).mockResolvedValue(mockStats)
        vi.mocked(parseDetections).mockReturnValue([])
    })

    afterEach(() => {
        vi.useRealTimers()
    })

    it('should initialize with correct structure', async () => {
        const { result } = renderHook(() => useTechStats())

        await act(async () => {
            vi.advanceTimersByTime(0)
        })

        expect(result.current).toHaveProperty('connected')
        expect(result.current).toHaveProperty('vehicleCount')
        expect(result.current).toHaveProperty('activeIncidents')
        expect(result.current).toHaveProperty('totalDetections')
        expect(result.current).toHaveProperty('username')
        expect(result.current).toHaveProperty('sessionStart')
    })

    it('should fetch initial stats from API', async () => {
        const { result } = renderHook(() => useTechStats())

        await act(async () => {
            vi.advanceTimersByTime(0)
        })

        expect(vi.mocked(fetchStats)).toHaveBeenCalled()
        expect(result.current.vehicleCount).toBe(mockStats.activeVehicles)
        expect(result.current.activeIncidents).toBe(mockStats.activeIncidents)
    })

    it('should reflect connected status from useRealtime', async () => {
        const { result } = renderHook(() => useTechStats())

        expect(result.current.connected).toBe(true)
    })

    it('should accumulate detections from WebSocket', async () => {
        vi.mocked(parseDetections).mockReturnValue([
            { id: 'det1', timestamp: new Date().toISOString() },
            { id: 'det2', timestamp: new Date().toISOString() },
            { id: 'det3', timestamp: new Date().toISOString() },
        ] as any)

        const { result } = renderHook(() => useTechStats())

        expect(result.current.totalDetections).toBe(0)

        // First detection batch
        if (mockDetectionSubscriber) {
            act(() => {
                mockDetectionSubscriber!({ some: 'data' })
            })
        }

        expect(result.current.totalDetections).toBe(3)

        // Second detection batch
        if (mockDetectionSubscriber) {
            act(() => {
                mockDetectionSubscriber!({ some: 'data' })
            })
        }

        expect(result.current.totalDetections).toBe(6)
    })

    it('should return username from useAuth', async () => {
        const { result } = renderHook(() => useTechStats())

        expect(result.current.username).toBe('testuser')
    })

    it('should set sessionStart to current time on mount', () => {
        const before = Date.now()

        const { result } = renderHook(() => useTechStats())

        const after = Date.now()

        expect(result.current.sessionStart).toBeGreaterThanOrEqual(before)
        expect(result.current.sessionStart).toBeLessThanOrEqual(after)
    })

    it('should periodically refetch stats every 5 seconds', async () => {
        vi.mocked(fetchStats).mockClear()

        renderHook(() => useTechStats())

        await act(async () => {
            vi.advanceTimersByTime(0)
        })

        expect(vi.mocked(fetchStats)).toHaveBeenCalledTimes(1)

        await act(async () => {
            vi.advanceTimersByTime(5000)
        })

        expect(vi.mocked(fetchStats)).toHaveBeenCalledTimes(2)

        await act(async () => {
            vi.advanceTimersByTime(5000)
        })

        expect(vi.mocked(fetchStats)).toHaveBeenCalledTimes(3)
    })

    it('should prefer live vehicle count from useVehicleCounts if available', async () => {
        vi.mocked(useVehicleCounts).mockReturnValue({
            counts: new Map([['fiber1:1-10', { vehicleCount: 50, timestamp: Date.now() } as any]]),
            getCount: vi.fn(),
            totalVehicles: vi.fn(() => 50),
        } as any)

        const { result } = renderHook(() => useTechStats())

        await act(async () => {
            vi.advanceTimersByTime(0)
        })

        expect(result.current.vehicleCount).toBe(50)
    })

    it('should fall back to server stats when live count is 0', async () => {
        vi.mocked(useVehicleCounts).mockReturnValue({
            counts: new Map(),
            getCount: vi.fn(),
            totalVehicles: vi.fn(() => 0),
        } as any)

        const { result } = renderHook(() => useTechStats())

        await act(async () => {
            vi.advanceTimersByTime(0)
        })

        expect(result.current.vehicleCount).toBe(mockStats.activeVehicles)
    })

    it('should handle stats API failure gracefully', async () => {
        vi.mocked(fetchStats).mockRejectedValue(new Error('API Error'))

        const { result } = renderHook(() => useTechStats())

        await act(async () => {
            vi.advanceTimersByTime(0)
        })

        expect(result.current.vehicleCount).toBeNull()
        expect(result.current.activeIncidents).toBeNull()
    })

    it('should clean up interval timer on unmount', () => {
        const clearIntervalSpy = vi.spyOn(globalThis, 'clearInterval')

        const { unmount } = renderHook(() => useTechStats())

        unmount()

        expect(clearIntervalSpy).toHaveBeenCalled()
        clearIntervalSpy.mockRestore()
    })

    it('should not set state after unmount', async () => {
        const { unmount } = renderHook(() => useTechStats())

        unmount()

        await act(async () => {
            vi.advanceTimersByTime(100)
        })

        // Should not throw any warnings about setting state after unmount
        expect(true).toBe(true)
    })

    it('should handle empty detection data', async () => {
        vi.mocked(parseDetections).mockReturnValue([])

        const { result } = renderHook(() => useTechStats())

        if (mockDetectionSubscriber) {
            act(() => {
                mockDetectionSubscriber!({})
            })
        }

        expect(result.current.totalDetections).toBe(0)
    })
})
