import { useState, useEffect, useCallback, type ReactNode } from 'react'
import i18next from 'i18next'
import { AuthContext } from './AuthContext'
import * as authApi from '@/api/auth'

const USERNAME_KEY = 'sequoia_auth_username'
const WIDGETS_KEY = 'sequoia_auth_widgets'
const LAYERS_KEY = 'sequoia_auth_layers'
const ORG_ID_KEY = 'sequoia_auth_org_id'
const ORG_NAME_KEY = 'sequoia_auth_org_name'

type AuthProviderProps = {
    children: ReactNode
}

function loadCachedArray(key: string, fallback: string[]): string[] {
    const cached = localStorage.getItem(key)
    if (cached) {
        try {
            const parsed = JSON.parse(cached)
            if (Array.isArray(parsed) && parsed.length > 0) return parsed
        } catch { /* ignore */ }
    }
    return fallback
}

function cacheAuthData(
    username: string,
    allowedWidgets: string[],
    allowedLayers: string[],
    organizationId: string | null,
    organizationName: string | null,
) {
    localStorage.setItem(USERNAME_KEY, username)
    localStorage.setItem(WIDGETS_KEY, JSON.stringify(allowedWidgets))
    localStorage.setItem(LAYERS_KEY, JSON.stringify(allowedLayers))
    if (organizationId) localStorage.setItem(ORG_ID_KEY, organizationId)
    if (organizationName) localStorage.setItem(ORG_NAME_KEY, organizationName)
}

function clearCachedAuthData() {
    localStorage.removeItem(USERNAME_KEY)
    localStorage.removeItem(WIDGETS_KEY)
    localStorage.removeItem(LAYERS_KEY)
    localStorage.removeItem(ORG_ID_KEY)
    localStorage.removeItem(ORG_NAME_KEY)
}

export function AuthProvider({ children }: AuthProviderProps) {
    const [isAuthenticated, setIsAuthenticated] = useState(false)
    const [isLoading, setIsLoading] = useState(true)
    const [username, setUsername] = useState<string | null>(null)
    const [organizationId, setOrganizationId] = useState<string | null>(() =>
        localStorage.getItem(ORG_ID_KEY)
    )
    const [organizationName, setOrganizationName] = useState<string | null>(() =>
        localStorage.getItem(ORG_NAME_KEY)
    )
    const [allowedWidgets, setAllowedWidgets] = useState<string[]>(() =>
        loadCachedArray(WIDGETS_KEY, ['map', 'traffic_monitor', 'incidents'])
    )
    const [allowedLayers, setAllowedLayers] = useState<string[]>(() =>
        loadCachedArray(LAYERS_KEY, ['landmarks', 'sections', 'detections', 'incidents'])
    )

    // On mount: try to restore session via httpOnly refresh cookie
    // (since the access token is in-memory, it's lost on page reload)
    useEffect(() => {
        const restoreSession = async () => {
            // First try refresh via cookie to get a new access token
            const result = await authApi.verifyToken()

            if (result.valid && result.data) {
                setIsAuthenticated(true)
                setUsername(result.data.username)
                setOrganizationId(result.data.organizationId ?? null)
                setOrganizationName(result.data.organizationName ?? null)
                setAllowedWidgets(result.data.allowedWidgets)
                setAllowedLayers(result.data.allowedLayers)
                cacheAuthData(
                    result.data.username,
                    result.data.allowedWidgets,
                    result.data.allowedLayers,
                    result.data.organizationId ?? null,
                    result.data.organizationName ?? null,
                )
            } else {
                // No valid session, clear cached display data
                clearCachedAuthData()
            }

            setIsLoading(false)
        }

        restoreSession()
    }, [])

    // Proactively refresh access token before it expires (every 12 minutes)
    useEffect(() => {
        if (!isAuthenticated) return

        const interval = setInterval(async () => {
            const result = await authApi.verifyToken()
            if (!result.valid) {
                authApi.clearAuthToken()
                clearCachedAuthData()
                setIsAuthenticated(false)
                setUsername(null)
            }
        }, 12 * 60 * 1000) // 12min — refresh before 15min access token expires

        return () => clearInterval(interval)
    }, [isAuthenticated])

    const login = useCallback(async (usernameInput: string, password: string) => {
        try {
            const data = await authApi.login(usernameInput, password)

            setIsAuthenticated(true)
            setUsername(data.username)
            setOrganizationId(data.organizationId ?? null)
            setOrganizationName(data.organizationName ?? null)
            setAllowedWidgets(data.allowedWidgets ?? [])
            setAllowedLayers(data.allowedLayers ?? [])
            cacheAuthData(
                data.username,
                data.allowedWidgets ?? [],
                data.allowedLayers ?? [],
                data.organizationId ?? null,
                data.organizationName ?? null,
            )

            return { success: true }
        } catch (e) {
            if (e instanceof Error) {
                // Check for rate limiting
                if (e.message.includes('429') || e.message.toLowerCase().includes('too many')) {
                    return { success: false, error: i18next.t('auth.tooManyAttempts') }
                }
                return { success: false, error: e.message }
            }
            return { success: false, error: i18next.t('auth.connectionFailed') }
        }
    }, [])

    const logout = useCallback(async () => {
        await authApi.logout()
        clearCachedAuthData()
        setIsAuthenticated(false)
        setUsername(null)
        setOrganizationId(null)
        setOrganizationName(null)
        setAllowedWidgets([])
        setAllowedLayers([])
    }, [])

    return (
        <AuthContext.Provider value={{ isAuthenticated, isLoading, username, organizationId, organizationName, allowedWidgets, allowedLayers, login, logout }}>
            {children}
        </AuthContext.Provider>
    )
}
