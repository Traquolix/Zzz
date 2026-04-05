import { API_URL } from '@/constants/api'
import { getAccessToken } from '@/auth/oidc'
import i18n from '@/i18n'

type RequestOptions = {
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE' | 'PATCH'
  body?: unknown
  headers?: Record<string, string>
  requiresAuth?: boolean
}

const REQUEST_TIMEOUT_MS = 10_000

/**
 * Base API client with consistent error handling and OIDC auth.
 *
 * Gets the access token from oidc-client-ts on each request.
 * If the token is expired, oidc-client-ts handles silent renewal.
 */
export async function apiRequest<T>(endpoint: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, requiresAuth = true } = options

  const headers: Record<string, string> = {
    'Accept-Language': i18n.language,
  }

  if (requiresAuth) {
    const token = await getAccessToken()
    if (token) {
      headers['Authorization'] = `Bearer ${token}`
    } else {
      throw new ApiError(401, 'Not authenticated')
    }
  }

  if (body) {
    headers['Content-Type'] = 'application/json'
  }

  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS)

  const response = await fetch(`${API_URL}${endpoint}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
    signal: controller.signal,
  })
  clearTimeout(timeout)

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Request failed' }))
    throw new ApiError(response.status, error.detail || error.message || 'Request failed', error.code, error.errors)
  }

  // Handle empty responses
  const text = await response.text()
  if (!text) {
    if (method === 'DELETE' || method === 'PUT') return undefined as T
    throw new ApiError(0, 'Empty response body')
  }

  return JSON.parse(text)
}

export class ApiError extends Error {
  status: number
  code?: string
  errors?: string[]

  constructor(status: number, message: string, code?: string, errors?: string[]) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.errors = errors
  }
}

/**
 * Standard paginated response envelope from all list endpoints.
 */
export type PaginatedResponse<T> = {
  results: T[]
  hasMore: boolean
  limit: number
  offset: number
  total: number
}

/**
 * Fetch a paginated list endpoint and return the results array.
 * Throws if the response doesn't match the expected envelope shape.
 */
export async function apiPaginatedRequest<T>(
  endpoint: string,
  options: RequestOptions = {},
): Promise<PaginatedResponse<T>> {
  const raw = await apiRequest<unknown>(endpoint, options)
  if (!raw || typeof raw !== 'object' || !('results' in (raw as object))) {
    throw new ApiError(0, 'Invalid paginated response shape')
  }
  return raw as PaginatedResponse<T>
}
