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

  // On mount: try to restore session via httpOnly refresh cookie
  useEffect(() => {
    const restoreSession = async () => {
      const result = await authApi.verifyToken()

      if (result.valid && result.data) {
        setIsAuthenticated(true)
        setUsername(result.data.username)
      }

      setIsLoading(false)
    }

    restoreSession()
  }, [])

  // Proactively refresh access token before it expires (every 12 minutes)
  useEffect(() => {
    if (!isAuthenticated) return

    const interval = setInterval(
      async () => {
        const result = await authApi.verifyToken()
        if (!result.valid) {
          authApi.clearAuthToken()
          setIsAuthenticated(false)
          setUsername(null)
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
  }, [])

  return (
    <AuthContext.Provider value={{ isAuthenticated, isLoading, username, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}
