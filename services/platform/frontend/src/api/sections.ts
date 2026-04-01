import { apiRequest } from './client'

// Keep in sync with backend: services/platform/backend/apps/monitoring/views.py
export const MAX_SECTIONS_PER_ORG = 50

export interface ApiSection {
  id: string
  fiberId: string
  direction: 0 | 1
  name: string
  channelStart: number
  channelEnd: number
  expectedTravelTime: number | null
  isActive: boolean
  createdAt: string
}

export interface SectionHistoryPoint {
  time: number
  speed: number
  speedMax: number
  samples: number
  flow: number
  occupancy: number
}

export async function fetchSections(): Promise<ApiSection[]> {
  const res = await apiRequest<{ results: ApiSection[] }>('/api/sections')
  return res.results
}

export async function createSection(data: {
  fiberId: string
  direction: 0 | 1
  name: string
  channelStart: number
  channelEnd: number
}): Promise<ApiSection> {
  return apiRequest<ApiSection>('/api/sections', {
    method: 'POST',
    body: data,
  })
}

export async function renameSection(id: string, name: string): Promise<{ id: string; name: string }> {
  return apiRequest<{ id: string; name: string }>(`/api/sections/${id}`, {
    method: 'PATCH',
    body: { name },
  })
}

export async function deleteSection(id: string): Promise<void> {
  await apiRequest<void>(`/api/sections/${id}`, { method: 'DELETE' })
}

export async function fetchSectionHistory(
  id: string,
  minutes = 60,
  flow?: 'sim' | 'live',
  since?: number,
): Promise<{ sectionId: string; minutes: number; points: SectionHistoryPoint[] }> {
  const params = new URLSearchParams({ minutes: String(minutes) })
  if (flow) params.set('flow', flow)
  if (since != null) params.set('since', String(since))
  return apiRequest(`/api/sections/${id}/history?${params}`)
}

export async function fetchBatchSectionHistory(
  sectionIds: string[],
  minutes = 60,
  flow?: 'sim' | 'live',
  since?: Record<string, number>,
): Promise<Record<string, SectionHistoryPoint[]>> {
  const params = flow ? `?flow=${flow}` : ''
  const res = await apiRequest<{ results: Record<string, SectionHistoryPoint[]> }>(
    `/api/sections/batch-history${params}`,
    {
      method: 'POST',
      body: { sectionIds, minutes, ...(since && Object.keys(since).length > 0 && { since }) },
    },
  )
  return res.results
}
