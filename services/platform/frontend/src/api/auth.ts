import { apiRequest, getAuthToken, setAuthToken, clearAuthToken, attemptTokenRefresh } from './client'

export type AuthData = {
  username: string
  organizationId: string | null
  organizationName: string | null
  allowedWidgets: string[]
  allowedLayers: string[]
  role: string | null
  isSuperuser: boolean
}

type LoginResponse = AuthData & {
  token: string
}

type VerifyResponse = AuthData & {
  valid: boolean
}

/**
 * Verify the current session. If the in-memory token is missing
 * (e.g. after page reload), tries to refresh via httpOnly cookie first.
 */
export async function verifyToken(): Promise<{ valid: boolean; data?: AuthData }> {
  // If no in-memory token, try to restore via refresh cookie.
  // Skip if no session hint cookie — avoids a blind POST that always 401s.
  if (!getAuthToken()) {
    if (!document.cookie.includes('has_session=')) return { valid: false }
    const refreshed = await attemptTokenRefresh()
    if (!refreshed) return { valid: false }
  }

  try {
    const response = await apiRequest<VerifyResponse>('/api/auth/verify', {
      method: 'GET',
    })
    if (response.valid) {
      return {
        valid: true,
        data: {
          username: response.username,
          organizationId: response.organizationId ?? null,
          organizationName: response.organizationName ?? null,
          allowedWidgets: response.allowedWidgets ?? [],
          allowedLayers: response.allowedLayers ?? [],
          role: response.role ?? null,
          isSuperuser: response.isSuperuser ?? false,
        },
      }
    }
    return { valid: false }
  } catch {
    return { valid: false }
  }
}

/**
 * Login with username and password
 */
export async function login(username: string, password: string): Promise<LoginResponse> {
  const data = await apiRequest<LoginResponse>('/api/auth/login', {
    method: 'POST',
    body: { username, password },
    requiresAuth: false,
  })

  setAuthToken(data.token)
  return data
}

/**
 * Logout and clear token
 */
export async function logout(): Promise<void> {
  try {
    await apiRequest('/api/auth/logout', { method: 'POST' })
  } catch {
    // Ignore errors - we'll clear token anyway
  } finally {
    clearAuthToken()
    document.cookie = 'has_session=; path=/; max-age=0'
  }
}

// Re-export token utilities for direct access
export { getAuthToken, setAuthToken, clearAuthToken, attemptTokenRefresh }
