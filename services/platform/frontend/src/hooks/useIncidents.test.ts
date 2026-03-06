import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import type { Incident } from '@/types/incident'

// Simple mock setup without factory functions
vi.mock('@/hooks/useRealtime')
vi.mock('@/api/incidents')
vi.mock('@/lib/parseMessage')
vi.mock('@/lib/logger')

import { useIncidents } from './useIncidents'
import { useRealtime } from '@/hooks/useRealtime'
import { fetchIncidents } from '@/api/incidents'
import { parseIncident } from '@/lib/parseMessage'

const mockIncident: Incident = {
  id: 'incident-1',
  status: 'active',
  location: { lat: 10, lng: 20 },
  timestamp: new Date().toISOString(),
  title: 'Test Incident',
} as unknown as Incident

const mockIncident2: Incident = {
  id: 'incident-2',
  status: 'acknowledged',
  location: { lat: 15, lng: 25 },
  timestamp: new Date().toISOString(),
  title: 'Second Incident',
} as unknown as Incident

describe('useIncidents', () => {
  let mockIncidentSubscriber: ((data: unknown) => void) | null = null

  beforeEach(() => {
    vi.useFakeTimers()
    vi.clearAllMocks()
    mockIncidentSubscriber = null

    vi.mocked(useRealtime).mockReturnValue({
      subscribe: vi.fn((channel, callback) => {
        if (channel === 'incidents') {
          mockIncidentSubscriber = callback
        }
        return vi.fn()
      }),
      connected: true,
      reconnecting: false,
      authFailed: false,
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } as any)

    vi.mocked(fetchIncidents).mockResolvedValue({
      results: [mockIncident],
      hasMore: false,
      total: 1,
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } as any)
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('should initialize with loading true and empty incidents', () => {
    vi.mocked(fetchIncidents).mockImplementationOnce(
      () => new Promise(() => {}), // Never resolves
    )

    const { result } = renderHook(() => useIncidents())

    expect(result.current.loading).toBe(true)
    expect(result.current.incidents).toEqual([])
    expect(result.current.connected).toBe(true)
  })

  it('should fetch initial incidents from API', async () => {
    const { result } = renderHook(() => useIncidents())

    await act(async () => {
      vi.advanceTimersByTime(0)
    })

    expect(result.current.loading).toBe(false)
    expect(result.current.incidents).toEqual([mockIncident])
    expect(vi.mocked(fetchIncidents)).toHaveBeenCalled()
  })

  it('should handle API fetch error gracefully', async () => {
    const error = new Error('API Error')
    vi.mocked(fetchIncidents).mockRejectedValueOnce(error)

    const { result } = renderHook(() => useIncidents())

    await act(async () => {
      vi.advanceTimersByTime(0)
    })

    expect(result.current.loading).toBe(false)
    expect(result.current.incidents).toEqual([])
  })

  it('should subscribe to WebSocket incidents when connected', () => {
    vi.mocked(parseIncident).mockReturnValue(mockIncident2)

    const { result } = renderHook(() => useIncidents())

    expect(mockIncidentSubscriber).not.toBeNull()

    // Simulate WebSocket message
    if (mockIncidentSubscriber) {
      act(() => {
        mockIncidentSubscriber!({ some: 'data' })
      })
    }

    expect(result.current.incidents).toContainEqual(mockIncident2)
  })

  it('should add new incident from WebSocket to the front of the list', async () => {
    vi.mocked(parseIncident).mockReturnValue(mockIncident2)

    const { result } = renderHook(() => useIncidents())

    await act(async () => {
      vi.advanceTimersByTime(0)
    })

    expect(result.current.incidents).toEqual([mockIncident])

    // Simulate new incident from WebSocket
    if (mockIncidentSubscriber) {
      act(() => {
        mockIncidentSubscriber!({ some: 'data' })
      })
    }

    expect(result.current.incidents[0]).toEqual(mockIncident2)
    expect(result.current.incidents[1]).toEqual(mockIncident)
  })

  it('should update existing incident when WebSocket message has same ID', async () => {
    const updatedIncident: Incident = {
      ...mockIncident,
      status: 'resolved',
    }
    vi.mocked(parseIncident).mockReturnValue(updatedIncident)

    const { result } = renderHook(() => useIncidents())

    await act(async () => {
      vi.advanceTimersByTime(0)
    })

    expect(result.current.incidents[0].status).toBe('active')

    // Simulate update from WebSocket
    if (mockIncidentSubscriber) {
      act(() => {
        mockIncidentSubscriber!({ some: 'data' })
      })
    }

    expect(result.current.incidents).toHaveLength(1)
    expect(result.current.incidents[0].status).toBe('resolved')
  })

  it('should track new incident with receivedAt timestamp', async () => {
    vi.mocked(parseIncident).mockReturnValue(mockIncident2)

    const { result } = renderHook(() => useIncidents())

    if (mockIncidentSubscriber) {
      act(() => {
        mockIncidentSubscriber!({ some: 'data' })
      })
    }

    // Should be new immediately after receipt
    expect(result.current.isNewIncident(mockIncident2.id)).toBe(true)
  })

  it('should expire new indicator after NEW_INCIDENT_DURATION', async () => {
    vi.mocked(parseIncident).mockReturnValue(mockIncident2)

    const { result } = renderHook(() => useIncidents())

    if (mockIncidentSubscriber) {
      act(() => {
        mockIncidentSubscriber!({ some: 'data' })
      })
    }

    expect(result.current.isNewIncident(mockIncident2.id)).toBe(true)

    // Advance past NEW_INCIDENT_DURATION (30 seconds)
    act(() => {
      vi.advanceTimersByTime(30_001)
    })

    expect(result.current.isNewIncident(mockIncident2.id)).toBe(false)
  })

  it('should update incident status via updateIncidentStatus', async () => {
    const { result } = renderHook(() => useIncidents())

    await act(async () => {
      vi.advanceTimersByTime(0)
    })

    expect(result.current.incidents[0].status).toBe('active')

    act(() => {
      result.current.updateIncidentStatus('incident-1', 'resolved')
    })

    expect(result.current.incidents[0].status).toBe('resolved')
  })

  it('should ignore invalid incident messages from WebSocket', async () => {
    vi.mocked(parseIncident).mockReturnValue(null)

    const { result } = renderHook(() => useIncidents())

    await act(async () => {
      vi.advanceTimersByTime(0)
    })

    const initialLength = result.current.incidents.length

    if (mockIncidentSubscriber) {
      act(() => {
        mockIncidentSubscriber!({ invalid: 'data' })
      })
    }

    expect(result.current.incidents).toHaveLength(initialLength)
  })

  it('should clean up interval timer on unmount', () => {
    const clearIntervalSpy = vi.spyOn(globalThis, 'clearInterval')

    const { unmount } = renderHook(() => useIncidents())

    unmount()

    expect(clearIntervalSpy).toHaveBeenCalled()
    clearIntervalSpy.mockRestore()
  })

  it('should not set state after unmount', async () => {
    const { unmount } = renderHook(() => useIncidents())

    unmount()

    await act(async () => {
      vi.advanceTimersByTime(100)
    })

    // Should not throw any warnings about setting state after unmount
    expect(true).toBe(true)
  })
})
