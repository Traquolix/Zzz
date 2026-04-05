import { apiRequest } from './client'
import { getAccessToken } from '@/auth/oidc'
import { API_URL } from '@/constants/api'

export type ExportEstimate = {
  estimatedRows: number
  estimatedSize: number
  tier: string | null
}

export type ExportParams = {
  fiberId: string
  start: string
  end: string
  type: 'detections' | 'incidents'
  direction?: 0 | 1
  format?: 'csv' | 'json'
  tier?: string
  channelStart?: number
  channelEnd?: number
}

export async function fetchExportEstimate(params: {
  fiberId: string
  start: string
  end: string
  type: 'detections' | 'incidents'
  direction?: 0 | 1
  channelStart?: number
  channelEnd?: number
}): Promise<ExportEstimate> {
  const query = new URLSearchParams({
    fiber_id: params.fiberId,
    start: params.start,
    end: params.end,
    type: params.type,
  })
  if (params.direction !== undefined) {
    query.set('direction', String(params.direction))
  }
  if (params.channelStart !== undefined) {
    query.set('channel_start', String(params.channelStart))
  }
  if (params.channelEnd !== undefined) {
    query.set('channel_end', String(params.channelEnd))
  }
  return apiRequest<ExportEstimate>(`/api/export/estimate?${query}`)
}

export async function downloadExport(params: ExportParams): Promise<void> {
  const endpoint = params.type === 'incidents' ? '/api/export/incidents' : '/api/export/detections'
  const query = new URLSearchParams({
    fiber_id: params.fiberId,
    start: params.start,
    end: params.end,
    fmt: params.format ?? 'csv',
    flow: 'live',
  })
  if (params.direction !== undefined) {
    query.set('direction', String(params.direction))
  }
  if (params.tier) {
    query.set('tier', params.tier)
  }
  if (params.channelStart !== undefined) {
    query.set('channel_start', String(params.channelStart))
  }
  if (params.channelEnd !== undefined) {
    query.set('channel_end', String(params.channelEnd))
  }

  const token = await getAccessToken()
  const resp = await fetch(`${API_URL}${endpoint}?${query}`, {
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  })

  if (resp.status === 429) {
    throw new Error('export.rateLimitError')
  }
  if (!resp.ok) {
    const body = await resp.json().catch(() => null)
    throw new Error(body?.detail ?? 'export.failed')
  }

  const blob = await resp.blob()
  const ext = params.format === 'json' ? 'json' : 'csv'
  const filename = `sequoia_${params.type}_${params.fiberId}.${ext}`

  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  setTimeout(() => URL.revokeObjectURL(url), 100)
}
