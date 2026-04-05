import { apiRequest } from './client'

export type AuthData = {
  username: string
  organizationId: string | null
  organizationName: string | null
  allowedWidgets: string[]
  allowedLayers: string[]
  role: string | null
  isSuperuser: boolean
}

type VerifyResponse = AuthData & {
  valid: boolean
}

/**
 * Verify the current session by calling the backend verify endpoint.
 * The access token is attached automatically by apiRequest via oidc-client-ts.
 */
export async function verifyToken(): Promise<{ valid: boolean; data?: AuthData }> {
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
