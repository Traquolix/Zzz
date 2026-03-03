import { useState, useEffect, useCallback, type ReactNode } from 'react'
import i18next from 'i18next'
import { AuthContext } from './AuthContext'
import * as authApi from '@/api/auth'

const USERNAME_KEY = 'sequoia_auth_username'
const WIDGETS_KEY = 'sequoia_auth_widgets'
const LAYERS_KEY = 'sequoia_auth_layers'
const ORG_ID_KEY = 'sequoia_auth_org_id'
const ORG_NAME_KEY = 'sequoia_auth_org_name'
const ROLE_KEY = 'sequoia_auth_role'
const IS_SUPERUSER_KEY = 'sequoia_auth_is_superuser'

type AuthProviderProps = {
    children: ReactNode
}

function cacheAuthData(
    username: string,
    allowedWidgets: string[],
    allowedLayers: string[],
    organizationId: string | null,
    organizationName: string | null,
    role: string | null,
    isSuperuser: boolean,
) {
    localStorage.setItem(USERNAME_KEY, username)
    localStorage.setItem(WIDGETS_KEY, JSON.stringify(allowedWidgets))
    localStorage.setItem(LAYERS_KEY, JSON.stringify(allowedLayers))
    if (organizationId) localStorage.setItem(ORG_ID_KEY, organizationId)
    if (organizationName) localStorage.setItem(ORG_NAME_KEY, organizationName)
    if (role) localStorage.setItem(ROLE_KEY, role)
    localStorage.setItem(IS_SUPERUSER_KEY, JSON.stringify(isSuperuser))
}

function clearCachedAuthData() {
    localStorage.removeItem(USERNAME_KEY)
    localStorage.removeItem(WIDGETS_KEY)
    localStorage.removeItem(LAYERS_KEY)
    localStorage.removeItem(ORG_ID_KEY)
    localStorage.removeItem(ORG_NAME_KEY)
    localStorage.removeItem(ROLE_KEY)
    localStorage.removeItem(IS_SUPERUSER_KEY)
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
    // Don't trust cached permissions on initial load — start empty and wait for verifyToken()
    // This prevents using stale permissions from a previous session
    const [allowedWidgets, setAllowedWidgets] = useState<string[]>([])
    const [allowedLayers, setAllowedLayers] = useState<string[]>([])
    const [role, setRole] = useState<string | null>(null)
    const [isSuperuser, setIsSuperuser] = useState(false)

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
                setRole(result.data.role ?? null)
                setIsSuperuser(result.data.isSuperuser ?? false)
                cacheAuthData(
                    result.data.username,
                    result.data.allowedWidgets,
                    result.data.allowedLayers,
                    result.data.organizationId ?? null,
                    result.data.organizationName ?? null,
                    result.data.role ?? null,
                    result.data.isSuperuser ?? false,
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
                setRole(null)
                setIsSuperuser(false)
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
            setRole(data.role ?? null)
            setIsSuperuser(data.isSuperuser ?? false)
            cacheAuthData(
                data.username,
                data.allowedWidgets ?? [],
                data.allowedLayers ?? [],
                data.organizationId ?? null,
                data.organizationName ?? null,
                data.role ?? null,
                data.isSuperuser ?? false,
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
        setRole(null)
        setIsSuperuser(false)
    }, [])

    return (
        <AuthContext.Provider value={{ isAuthenticated, isLoading, username, organizationId, organizationName, allowedWidgets, allowedLayers, role, isSuperuser, login, logout }}>
            {children}
        </AuthContext.Provider>
    )
}
