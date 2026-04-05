import { createContext } from 'react'

export type AuthContextType = {
  isAuthenticated: boolean
  isLoading: boolean
  username: string | null
  role: string | null
  isSuperuser: boolean
  organizationName: string | null
  logout: () => Promise<void>
}

export const AuthContext = createContext<AuthContextType | null>(null)
