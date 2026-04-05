import { UserManager, WebStorageStateStore, type UserManagerSettings } from 'oidc-client-ts'
import { API_URL } from '@/constants/api'

let _userManager: UserManager | null = null
let _initPromise: Promise<UserManager> | null = null

/** OIDC config fetched from the backend at runtime. */
type OIDCConfig = {
  authority: string
  client_id: string
}

async function fetchOIDCConfig(): Promise<OIDCConfig> {
  const resp = await fetch(`${API_URL}/api/auth/oidc/config`)
  if (!resp.ok) throw new Error(`Failed to fetch OIDC config: ${resp.status}`)
  const config: OIDCConfig = await resp.json()
  if (!config.authority || !config.client_id) {
    throw new Error('OIDC not configured on the server')
  }
  return config
}

/**
 * Get or create the OIDC UserManager singleton.
 * Config is fetched from the backend on first call.
 * Concurrent callers share the same initialization promise.
 */
export async function getUserManager(): Promise<UserManager> {
  if (_userManager) return _userManager

  if (!_initPromise) {
    _initPromise = (async () => {
      const config = await fetchOIDCConfig()

      const settings: UserManagerSettings = {
        authority: config.authority,
        client_id: config.client_id,
        redirect_uri: `${window.location.origin}/auth/callback`,
        post_logout_redirect_uri: `${window.location.origin}/login`,
        response_type: 'code',
        scope: 'openid profile email',
        automaticSilentRenew: true,
        userStore: new WebStorageStateStore({ store: sessionStorage }),
      }

      _userManager = new UserManager(settings)
      return _userManager
    })()
  }

  return _initPromise
}

/**
 * Get the current access token, or null if not authenticated.
 */
export async function getAccessToken(): Promise<string | null> {
  const mgr = await getUserManager()
  const user = await mgr.getUser()
  if (!user || user.expired) return null
  return user.access_token
}
