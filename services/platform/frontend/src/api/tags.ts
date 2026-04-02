import { apiRequest } from './client'
import type { IncidentTag } from '@/types/incident'

export async function fetchTags(): Promise<IncidentTag[]> {
  const data = await apiRequest<{ results: IncidentTag[] }>('/api/admin/tags?limit=200')
  return data.results
}

export async function createTag(name: string, color: string): Promise<IncidentTag> {
  return apiRequest<IncidentTag>('/api/admin/tags', {
    method: 'POST',
    body: { name, color },
  })
}

export async function updateTag(id: string, data: { name?: string; color?: string }): Promise<IncidentTag> {
  return apiRequest<IncidentTag>(`/api/admin/tags/${id}`, {
    method: 'PATCH',
    body: data,
  })
}

export async function deleteTag(id: string): Promise<void> {
  await apiRequest<void>(`/api/admin/tags/${id}`, { method: 'DELETE' })
}
