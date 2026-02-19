import { createContext } from 'react'

export type AuthContextType = {
    isAuthenticated: boolean
    isLoading: boolean
    username: string | null
    organizationId: string | null
    organizationName: string | null
    allowedWidgets: string[]
    allowedLayers: string[]
    login: (username: string, password: string) => Promise<{ success: boolean; error?: string }>
    logout: () => Promise<void>
}

export const AuthContext = createContext<AuthContextType | null>(null)
