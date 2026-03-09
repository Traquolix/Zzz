import { apiRequest } from './client'

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

export async function deleteSection(id: string): Promise<void> {
  await apiRequest<void>(`/api/sections/${id}`, { method: 'DELETE' })
}

export async function fetchSectionHistory(
  id: string,
  minutes = 60,
): Promise<{ sectionId: string; minutes: number; points: SectionHistoryPoint[] }> {
  return apiRequest(`/api/sections/${id}/history?minutes=${minutes}`)
}
