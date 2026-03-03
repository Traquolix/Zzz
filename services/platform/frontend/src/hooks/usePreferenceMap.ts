/**
 * Hook for Map state backed by user preferences with debounced persistence.
 *
 * Extracts the repeated pattern from SectionProvider, LandmarkDataProvider,
 * and SpeedLimitProvider:
 *   1. Load initial data from user preferences (once)
 *   2. Provide a Map<K, V> state
 *   3. Debounce-save back to preferences on changes
 *
 * Each provider still owns its domain logic (CRUD operations, key generation).
 * This hook just handles the init + persistence plumbing.
 */
import { useState, useCallback, useEffect, useRef } from 'react'
import { useUserPreferences } from '@/hooks/useUserPreferences'
import { useDebouncedSync } from '@/hooks/useDebouncedSync'
import type { UserPreferences } from '@/types/user'

type UsePreferenceMapConfig<K, V> = {
    /** Extract stored data from loaded preferences and convert to Map */
    load: (prefs: UserPreferences) => Map<K, V> | null
    /** Build a partial preferences update from the current Map */
    save: (map: Map<K, V>, currentPrefs: UserPreferences | null) => Partial<UserPreferences>
}

type UsePreferenceMapResult<K, V> = {
    map: Map<K, V>
    setMap: React.Dispatch<React.SetStateAction<Map<K, V>>>
    /** Call after mutating via setMap to schedule a debounced save */
    scheduleSave: (map: Map<K, V>) => void
    isLoading: boolean
}

export function usePreferenceMap<K, V>(
    config: UsePreferenceMapConfig<K, V>,
): UsePreferenceMapResult<K, V> {
    const { preferences, updatePreferences, isLoading: prefsLoading } = useUserPreferences()
    const [map, setMap] = useState<Map<K, V>>(new Map())
    const initializedRef = useRef(false)

    // Load from preferences once
    useEffect(() => {
        if (prefsLoading || initializedRef.current) return
        initializedRef.current = true

        if (preferences) {
            const loaded = config.load(preferences)
            if (loaded && loaded.size > 0) {
                setMap(loaded)
            }
        }
    }, [prefsLoading, preferences, config])

    // Debounced save
    const scheduleSave = useDebouncedSync(
        useCallback((newMap: Map<K, V>) => {
            const partial = config.save(newMap, preferences)
            updatePreferences({
                ...preferences,
                ...partial,
            })
        }, [preferences, updatePreferences, config]),
    )

    return { map, setMap, scheduleSave, isLoading: prefsLoading }
}
