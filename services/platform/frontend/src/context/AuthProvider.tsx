import { useState, useEffect, useCallback, useRef, type ReactNode } from 'react'
import { AuthContext } from './AuthContext'
import { getUserManager } from '@/auth/oidc'
import * as authApi from '@/api/auth'

type AuthProviderProps = {
  children: ReactNode
}

export function AuthProvider({ children }: AuthProviderProps) {
  const [isAuthenticated, setIsAuthenticated] = useState(false)
  const [isLoading, setIsLoading] = useState(true)
  const [username, setUsername] = useState<string | null>(null)
  const [role, setRole] = useState<string | null>(null)
  const [isSuperuser, setIsSuperuser] = useState(false)
  const [organizationName, setOrganizationName] = useState<string | null>(null)
  const mountedRef = useRef(true)

  const updateUserInfo = useCallback(async () => {
    const result = await authApi.verifyToken()
    if (!mountedRef.current) return
    if (result.valid && result.data) {
      setIsAuthenticated(true)
      setUsername(result.data.username)
      setRole(result.data.role)
      setIsSuperuser(result.data.isSuperuser)
      setOrganizationName(result.data.organizationName)
    }
  }, [])

  const clearAuthState = useCallback(() => {
    setIsAuthenticated(false)
    setUsername(null)
    setRole(null)
    setIsSuperuser(false)
    setOrganizationName(null)
  }, [])

  // On mount: check if OIDC session exists
  useEffect(() => {
    mountedRef.current = true
    const restoreSession = async () => {
      try {
        const mgr = await getUserManager()
        const user = await mgr.getUser()
        if (user && !user.expired) {
          await updateUserInfo()
        }
      } catch {
        // No session or failed to verify
      }
      if (mountedRef.current) setIsLoading(false)
    }

    restoreSession()
    return () => {
      mountedRef.current = false
    }
  }, [updateUserInfo])

  // Listen for token renewal events from oidc-client-ts
  useEffect(() => {
    let cancelled = false
    let removeListeners: (() => void) | undefined

    const setupListeners = async () => {
      const mgr = await getUserManager()
      if (cancelled) return

      const onUserLoaded = () => {
        // Token silently renewed — re-fetch user info from backend
        // in case role/org changed in Authentik
        updateUserInfo()
      }

      mgr.events.addUserLoaded(onUserLoaded)
      mgr.events.addUserUnloaded(clearAuthState)
      mgr.events.addSilentRenewError(clearAuthState)

      removeListeners = () => {
        mgr.events.removeUserLoaded(onUserLoaded)
        mgr.events.removeUserUnloaded(clearAuthState)
        mgr.events.removeSilentRenewError(clearAuthState)
      }
    }

    setupListeners()
    return () => {
      cancelled = true
      removeListeners?.()
    }
  }, [updateUserInfo, clearAuthState])

  const logout = useCallback(async () => {
    try {
      const mgr = await getUserManager()
      await mgr.signoutRedirect()
    } catch {
      // If signout redirect fails, clear local state anyway
    }
    clearAuthState()
  }, [clearAuthState])

  return (
    <AuthContext.Provider value={{ isAuthenticated, isLoading, username, role, isSuperuser, organizationName, logout }}>
      {children}
    </AuthContext.Provider>
  )
}
