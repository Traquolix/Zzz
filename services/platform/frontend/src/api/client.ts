import { API_URL } from '@/constants/api'
import i18n from '@/i18n'

// In-memory token storage — not persisted to localStorage
let _token: string | null = null

type RequestOptions = {
    method?: 'GET' | 'POST' | 'PUT' | 'DELETE' | 'PATCH'
    body?: unknown
    headers?: Record<string, string>
    requiresAuth?: boolean
}

let refreshPromise: Promise<boolean> | null = null

const REQUEST_TIMEOUT_MS = 10_000

/**
 * Attempt to refresh the access token using the httpOnly refresh cookie.
 * Returns true if refresh succeeded.
 * Exported so auth.ts can use the same logic with deduplication.
 */
export async function attemptTokenRefresh(): Promise<boolean> {
    if (refreshPromise) {
        return refreshPromise
    }

    refreshPromise = (async () => {
        try {
            const controller = new AbortController()
            const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS)
            const response = await fetch(`${API_URL}/api/auth/refresh`, {
                method: 'POST',
                credentials: 'include',
                signal: controller.signal,
            })
            clearTimeout(timeout)
            if (response.ok) {
                const data = await response.json()
                if (data.token) {
                    setAuthToken(data.token)
                    return true
                }
            }
            return false
        } catch {
            return false
        } finally {
            refreshPromise = null
        }
    })()

    return refreshPromise
}

/**
 * Base API client with consistent error handling, auth, and automatic token refresh.
 */
export async function apiRequest<T>(
    endpoint: string,
    options: RequestOptions = {}
): Promise<T> {
    const { method = 'GET', body, requiresAuth = true } = options

    const headers: Record<string, string> = {
        'Accept-Language': i18n.language,
    }

    if (requiresAuth) {
        const token = getAuthToken()
        if (token) {
            headers['Authorization'] = `Bearer ${token}`
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
        credentials: 'include',
        body: body ? JSON.stringify(body) : undefined,
        signal: controller.signal,
    })
    clearTimeout(timeout)

    // On 401, attempt token refresh and retry once
    if (response.status === 401 && requiresAuth) {
        const refreshed = await attemptTokenRefresh()
        if (refreshed) {
            const retryHeaders: Record<string, string> = {
                'Accept-Language': i18n.language,
            }
            const newToken = getAuthToken()
            if (newToken) {
                retryHeaders['Authorization'] = `Bearer ${newToken}`
            }
            if (body) {
                retryHeaders['Content-Type'] = 'application/json'
            }

            const retryController = new AbortController()
            const retryTimeout = setTimeout(() => retryController.abort(), REQUEST_TIMEOUT_MS)
            const retryResponse = await fetch(`${API_URL}${endpoint}`, {
                method,
                headers: retryHeaders,
                credentials: 'include',
                body: body ? JSON.stringify(body) : undefined,
                signal: retryController.signal,
            })
            clearTimeout(retryTimeout)

            if (!retryResponse.ok) {
                const error = await retryResponse.json().catch(() => ({ detail: 'Request failed' }))
                throw new ApiError(retryResponse.status, error.detail || error.message || 'Request failed', error.code, error.errors)
            }

            const text = await retryResponse.text()
            if (!text) {
                if (method === 'DELETE' || method === 'PUT') return undefined as T
                throw new ApiError(0, 'Empty response body')
            }
            return JSON.parse(text)
        }
    }

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

/**
 * Get stored auth token (in-memory only)
 */
export function getAuthToken(): string | null {
    return _token
}

/**
 * Set auth token (in-memory only)
 */
export function setAuthToken(token: string): void {
    _token = token
}

/**
 * Clear auth token
 */
export function clearAuthToken(): void {
    _token = null
}
