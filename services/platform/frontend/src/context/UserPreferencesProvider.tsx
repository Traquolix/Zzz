import { useState, useEffect, useCallback, useRef, type ReactNode } from 'react'
import { toast } from 'sonner'
import { UserPreferencesContext } from './UserPreferencesContext'
import { useAuth } from '@/hooks/useAuth'
import type { UserPreferences } from '@/types/user'
import * as preferencesApi from '@/api/preferences'

export function UserPreferencesProvider({ children }: { children: ReactNode }) {
    const { isAuthenticated, isLoading: authLoading } = useAuth()
    const [preferences, setPreferences] = useState<UserPreferences | null>(null)
    const [isLoading, setIsLoading] = useState(true)
    const [isSaving, setIsSaving] = useState(false)

    // Load preferences when authenticated
    useEffect(() => {
        if (authLoading) return

        if (!isAuthenticated) {
            setPreferences(null)
            setIsLoading(false)
            return
        }

        const load = async () => {
            setIsLoading(true)
            const prefs = await preferencesApi.loadPreferences()
            setPreferences(prefs)
            setIsLoading(false)
        }

        load()
    }, [isAuthenticated, authLoading])

    // Track consecutive failures to avoid spamming toasts
    const failureCountRef = useRef(0)
    const MAX_SILENT_FAILURES = 2

    const savePreferences = useCallback(async (prefs: UserPreferences) => {
        setIsSaving(true)
        try {
            await preferencesApi.savePreferences(prefs)
            setPreferences(prefs)
            failureCountRef.current = 0 // Reset on success
        } catch (error) {
            failureCountRef.current++
            // Only show toast after a few silent failures to avoid noise on transient issues
            if (failureCountRef.current >= MAX_SILENT_FAILURES) {
                toast.error('Failed to save preferences. Changes may not persist.', {
                    id: 'preferences-save-error', // Prevent duplicate toasts
                    duration: 5000,
                })
            }
            console.error('Failed to save preferences:', error)
            // Still update local state so UI remains responsive
            setPreferences(prefs)
        } finally {
            setIsSaving(false)
        }
    }, [])

    const updatePreferences = useCallback(async (partial: Partial<UserPreferences>) => {
        const updated = { ...preferences, ...partial }
        await savePreferences(updated)
    }, [preferences, savePreferences])

    return (
        <UserPreferencesContext.Provider value={{
            preferences,
            isLoading,
            isSaving,
            savePreferences,
            updatePreferences
        }}>
            {children}
        </UserPreferencesContext.Provider>
    )
}
