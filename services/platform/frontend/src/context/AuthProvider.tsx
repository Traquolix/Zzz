import { useState, useEffect, useCallback, type ReactNode } from 'react'
import { AuthContext } from './AuthContext'
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

  // On mount: try to restore session via httpOnly refresh cookie
  useEffect(() => {
    const restoreSession = async () => {
      const result = await authApi.verifyToken()

      if (result.valid && result.data) {
        setIsAuthenticated(true)
        setUsername(result.data.username)
        setRole(result.data.role)
        setIsSuperuser(result.data.isSuperuser)
        setOrganizationName(result.data.organizationName)
      }

      setIsLoading(false)
    }

    restoreSession()
  }, [])

  // Proactively refresh the access token before it expires.
  // The access token lifetime is 15 minutes; refresh every 12 minutes so the
  // token is always valid and we never trigger a 401 → refresh → retry cycle.
  useEffect(() => {
    if (!isAuthenticated) return

    const interval = setInterval(
      async () => {
        const refreshed = await authApi.attemptTokenRefresh()
        if (!refreshed) {
          authApi.clearAuthToken()
          setIsAuthenticated(false)
          setUsername(null)
          setRole(null)
          setIsSuperuser(false)
          setOrganizationName(null)
        }
      },
      12 * 60 * 1000,
    )

    return () => clearInterval(interval)
  }, [isAuthenticated])

  const login = useCallback(async (usernameInput: string, password: string) => {
    try {
      const data = await authApi.login(usernameInput, password)
      setIsAuthenticated(true)
      setUsername(data.username)
      setRole(data.role)
      setIsSuperuser(data.isSuperuser)
      setOrganizationName(data.organizationName)
      return { success: true }
    } catch (e) {
      if (e instanceof Error) {
        if (e.message.includes('429') || e.message.toLowerCase().includes('too many')) {
          return { success: false, error: 'Too many attempts. Please try again later.' }
        }
        return { success: false, error: e.message }
      }
      return { success: false, error: 'Connection failed. Please try again.' }
    }
  }, [])

  const logout = useCallback(async () => {
    await authApi.logout()
    setIsAuthenticated(false)
    setUsername(null)
    setRole(null)
    setIsSuperuser(false)
    setOrganizationName(null)
  }, [])

  return (
    <AuthContext.Provider
      value={{ isAuthenticated, isLoading, username, role, isSuperuser, organizationName, login, logout }}
    >
      {children}
    </AuthContext.Provider>
  )
}
