/**
 * Tests for incident workflow API client functions.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock client before importing
vi.mock('./client', () => ({
  apiPaginatedRequest: vi.fn(),
  apiRequest: vi.fn(),
}))

import { fetchIncidentActions, postIncidentAction } from './incidents'
import { apiRequest } from './client'

const mockApiRequest = vi.mocked(apiRequest)

describe('fetchIncidentActions', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('calls the correct endpoint', async () => {
    mockApiRequest.mockResolvedValueOnce({
      currentStatus: 'active',
      actions: [],
    })
    await fetchIncidentActions('inc-001')
    expect(mockApiRequest).toHaveBeenCalledWith('/api/incidents/inc-001/actions')
  })

  it('returns action history with correct shape', async () => {
    const mockHistory = {
      currentStatus: 'investigating',
      actions: [
        {
          id: 'a1',
          fromStatus: 'acknowledged',
          toStatus: 'investigating',
          performedBy: 'operator1',
          note: 'Checking cameras',
          performedAt: '2026-02-28T10:00:00Z',
        },
        {
          id: 'a2',
          fromStatus: 'active',
          toStatus: 'acknowledged',
          performedBy: 'operator1',
          note: '',
          performedAt: '2026-02-28T09:55:00Z',
        },
      ],
    }
    mockApiRequest.mockResolvedValueOnce(mockHistory)
    const result = await fetchIncidentActions('inc-002')
    expect(result.currentStatus).toBe('investigating')
    expect(result.actions).toHaveLength(2)
    expect(result.actions[0].toStatus).toBe('investigating')
  })
})

describe('postIncidentAction', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('posts acknowledge action with note', async () => {
    mockApiRequest.mockResolvedValueOnce({
      id: 'a1',
      fromStatus: 'active',
      toStatus: 'acknowledged',
      performedBy: 'operator1',
      note: 'On it',
      performedAt: '2026-02-28T10:00:00Z',
    })

    const result = await postIncidentAction('inc-001', 'acknowledged', 'On it')

    expect(mockApiRequest).toHaveBeenCalledWith('/api/incidents/inc-001/actions', {
      method: 'POST',
      body: { action: 'acknowledged', note: 'On it' },
    })
    expect(result.toStatus).toBe('acknowledged')
  })

  it('posts resolve action without note', async () => {
    mockApiRequest.mockResolvedValueOnce({
      id: 'a2',
      fromStatus: 'investigating',
      toStatus: 'resolved',
      performedBy: 'operator1',
      note: '',
      performedAt: '2026-02-28T10:05:00Z',
    })

    await postIncidentAction('inc-001', 'resolved')

    expect(mockApiRequest).toHaveBeenCalledWith('/api/incidents/inc-001/actions', {
      method: 'POST',
      body: { action: 'resolved', note: '' },
    })
  })
})
