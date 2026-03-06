import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useIncidentSnapshot } from './useIncidentSnapshot'
import { ApiError } from '@/api/client'
import type { IncidentSnapshot } from '@/types/incident'

// Mock the API module
vi.mock('@/api/incidents', () => ({
  fetchIncidentSnapshot: vi.fn(),
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'en', changeLanguage: vi.fn() },
  }),
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))

import { fetchIncidentSnapshot } from '@/api/incidents'

describe('useIncidentSnapshot', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('initializes with null snapshot and false loading', () => {
    const { result } = renderHook(() => useIncidentSnapshot())

    expect(result.current.snapshot).toBeNull()
    expect(result.current.loading).toBe(false)
    expect(result.current.error).toBeNull()
  })

  it('fetches snapshot and sets state correctly', async () => {
    const mockSnapshot: IncidentSnapshot = {
      incidentId: 'incident-1',
      fiberLine: 'fiber-1',
      centerChannel: 5,
      capturedAt: Date.now(),
      detections: [
        {
          fiberLine: 'fiber-1',
          channel: 5,
          speed: 45.5,
          count: 10,
          direction: 0,
          timestamp: Date.now(),
        },
      ],
    }

    vi.mocked(fetchIncidentSnapshot).mockResolvedValueOnce(mockSnapshot)

    const { result } = renderHook(() => useIncidentSnapshot())

    expect(result.current.loading).toBe(false)

    await act(async () => {
      await result.current.fetchSnapshot('incident-1')
    })

    expect(result.current.snapshot).toEqual(mockSnapshot)
    expect(result.current.loading).toBe(false)
    expect(result.current.error).toBeNull()
  })

  it('sets loading state to false after fetch completes', async () => {
    const mockSnapshot: IncidentSnapshot = {
      incidentId: 'incident-1',
      fiberLine: 'fiber-1',
      centerChannel: 5,
      capturedAt: Date.now(),
      detections: [],
    }

    vi.mocked(fetchIncidentSnapshot).mockResolvedValueOnce(mockSnapshot)

    const { result } = renderHook(() => useIncidentSnapshot())

    expect(result.current.loading).toBe(false)

    await act(async () => {
      await result.current.fetchSnapshot('incident-1')
    })

    expect(result.current.loading).toBe(false)
    expect(result.current.snapshot).toEqual(mockSnapshot)
  })

  it('handles 404 error with specific message', async () => {
    const apiError = new ApiError(404, 'Not found')

    vi.mocked(fetchIncidentSnapshot).mockRejectedValueOnce(apiError)

    const { result } = renderHook(() => useIncidentSnapshot())

    await act(async () => {
      await result.current.fetchSnapshot('incident-999')
    })

    expect(result.current.error).toBe('common.noSnapshot')
    expect(result.current.snapshot).toBeNull()
    expect(result.current.loading).toBe(false)
  })

  it('handles API error with generic message', async () => {
    const apiError = new ApiError(500, 'Internal server error')

    vi.mocked(fetchIncidentSnapshot).mockRejectedValueOnce(apiError)

    const { result } = renderHook(() => useIncidentSnapshot())

    await act(async () => {
      await result.current.fetchSnapshot('incident-1')
    })

    expect(result.current.error).toBe('common.somethingWentWrong')
    expect(result.current.snapshot).toBeNull()
    expect(result.current.loading).toBe(false)
  })

  it('clears snapshot and error on clearSnapshot call', async () => {
    const mockSnapshot: IncidentSnapshot = {
      incidentId: 'incident-1',
      fiberLine: 'fiber-1',
      centerChannel: 5,
      capturedAt: Date.now(),
      detections: [],
    }

    vi.mocked(fetchIncidentSnapshot).mockResolvedValueOnce(mockSnapshot)

    const { result } = renderHook(() => useIncidentSnapshot())

    await act(async () => {
      await result.current.fetchSnapshot('incident-1')
    })

    expect(result.current.snapshot).not.toBeNull()

    act(() => {
      result.current.clearSnapshot()
    })

    expect(result.current.snapshot).toBeNull()
    expect(result.current.error).toBeNull()
  })

  it('clears previous error when fetching again', async () => {
    const apiError = new ApiError(500, 'Error')
    const mockSnapshot: IncidentSnapshot = {
      incidentId: 'incident-1',
      fiberLine: 'fiber-1',
      centerChannel: 5,
      capturedAt: Date.now(),
      detections: [],
    }

    vi.mocked(fetchIncidentSnapshot).mockRejectedValueOnce(apiError)

    const { result } = renderHook(() => useIncidentSnapshot())

    // First fetch fails
    await act(async () => {
      await result.current.fetchSnapshot('incident-1')
    })

    expect(result.current.error).not.toBeNull()

    // Second fetch succeeds
    vi.mocked(fetchIncidentSnapshot).mockResolvedValueOnce(mockSnapshot)

    await act(async () => {
      await result.current.fetchSnapshot('incident-1')
    })

    expect(result.current.error).toBeNull()
    expect(result.current.snapshot).toEqual(mockSnapshot)
  })
})
