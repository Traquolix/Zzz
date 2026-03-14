import { createContext } from 'react'

export type AuthContextType = {
  isAuthenticated: boolean
  isLoading: boolean
  username: string | null
  role: string | null
  isSuperuser: boolean
  organizationName: string | null
  login: (username: string, password: string) => Promise<{ success: boolean; error?: string }>
  logout: () => Promise<void>
}

export const AuthContext = createContext<AuthContextType | null>(null)
