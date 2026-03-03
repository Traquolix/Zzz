import { useState, useEffect, useCallback, useRef, type ReactNode } from 'react'
import { showToast } from '@/lib/toast'
import { UserPreferencesContext } from './UserPreferencesContext'
import { useAuth } from '@/hooks/useAuth'
import type { UserPreferences } from '@/types/user'
import * as preferencesApi from '@/api/preferences'
import { logger } from '@/lib/logger'

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

    // Track latest committed preferences for rollback on save failure
    const committedPrefsRef = useRef<UserPreferences | null>(null)

    // Keep ref in sync with successfully loaded/saved preferences
    useEffect(() => {
        if (preferences && !isSaving) {
            committedPrefsRef.current = preferences
        }
    }, [preferences, isSaving])

    const savePreferences = useCallback(async (prefs: UserPreferences) => {
        setIsSaving(true)
        const rollback = committedPrefsRef.current
        // Optimistic update: show new value immediately
        setPreferences(prefs)
        try {
            await preferencesApi.savePreferences(prefs)
            committedPrefsRef.current = prefs
            failureCountRef.current = 0
        } catch (error) {
            failureCountRef.current++
            if (failureCountRef.current >= MAX_SILENT_FAILURES) {
                showToast.error('Failed to save preferences. Changes may not persist.')
            }
            logger.error('Failed to save preferences:', error)
            // Revert to last successfully committed state
            setPreferences(rollback)
        } finally {
            setIsSaving(false)
        }
    }, [])

    // Use functional setState to read latest preferences, avoiding stale closure.
    // This ensures concurrent partial updates (e.g., two toggles in quick succession)
    // don't clobber each other.
    const updatePreferences = useCallback(async (partial: Partial<UserPreferences>) => {
        let merged: UserPreferences | null = null
        setPreferences(prev => {
            merged = { ...prev, ...partial } as UserPreferences
            return merged
        })
        if (merged) {
            await savePreferences(merged)
        }
    }, [savePreferences])

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
