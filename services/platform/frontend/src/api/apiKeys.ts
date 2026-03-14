import { apiRequest } from './client'
import type { APIKeyInfo, CreateAPIKeyResponse } from '@/types/admin'

export async function fetchAPIKeys(): Promise<APIKeyInfo[]> {
  const data = await apiRequest<{ results: APIKeyInfo[] }>('/api/admin/api-keys')
  return data.results
}

export async function createAPIKey(name: string, expiresAt?: string): Promise<CreateAPIKeyResponse> {
  return apiRequest<CreateAPIKeyResponse>('/api/admin/api-keys', {
    method: 'POST',
    body: { name, ...(expiresAt ? { expiresAt } : {}) },
  })
}

export async function revokeAPIKey(keyId: string): Promise<void> {
  await apiRequest<void>(`/api/admin/api-keys/${keyId}`, { method: 'DELETE' })
}

export async function rotateAPIKey(keyId: string): Promise<CreateAPIKeyResponse> {
  return apiRequest<CreateAPIKeyResponse>(`/api/admin/api-keys/${keyId}/rotate`, {
    method: 'POST',
  })
}
