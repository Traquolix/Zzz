import { useState, useCallback, useEffect, type ReactNode } from 'react'
import { LandmarkDataContext, type LandmarkEntry } from './LandmarkSelectionContext'
import { useUserPreferences } from '@/hooks/useUserPreferences'
import { useDebouncedSync } from '@/hooks/useDebouncedSync'
import type { StoredLandmark } from '@/types/user'

function landmarkKey(fiberId: string, channel: number): string {
    return `${fiberId}:${channel}`
}

function landmarksToMap(landmarks: StoredLandmark[]): Map<string, LandmarkEntry> {
    const map = new Map<string, LandmarkEntry>()
    for (const l of landmarks) {
        map.set(landmarkKey(l.fiberId, l.channel), {
            name: l.name,
            favorite: l.favorite ?? false
        })
    }
    return map
}

function mapToLandmarks(map: Map<string, LandmarkEntry>): StoredLandmark[] {
    const landmarks: StoredLandmark[] = []
    for (const [key, entry] of map) {
        // Key format is "fiberId:channel" where fiberId can contain ":" (e.g., "carros:0:150")
        const lastColonIdx = key.lastIndexOf(':')
        if (lastColonIdx === -1) continue

        const fiberId = key.slice(0, lastColonIdx)
        const channel = parseInt(key.slice(lastColonIdx + 1), 10)

        if (fiberId && !isNaN(channel)) {
            landmarks.push({
                fiberId,
                channel,
                name: entry.name,
                favorite: entry.favorite || undefined
            })
        }
    }
    return landmarks
}

/**
 * Provider for landmark data (names, favorites).
 * Selection state is managed by MapSelectionProvider.
 */
export function LandmarkDataProvider({ children }: { children: ReactNode }) {
    const { preferences, updatePreferences, isLoading: prefsLoading } = useUserPreferences()

    const [landmarks, setLandmarks] = useState<Map<string, LandmarkEntry>>(new Map())
    const [initialized, setInitialized] = useState(false)

    // Initialize from server preferences
    useEffect(() => {
        if (prefsLoading || initialized) return

        const savedLandmarks = preferences?.map?.landmarks
        if (savedLandmarks && savedLandmarks.length > 0) {
            setLandmarks(landmarksToMap(savedLandmarks))
        }

        setInitialized(true)
    }, [prefsLoading, preferences, initialized])

    // Debounced save to server
    const saveToServer = useDebouncedSync(
        useCallback((newLandmarks: Map<string, LandmarkEntry>) => {
            updatePreferences({
                ...preferences,
                map: {
                    ...preferences?.map,
                    landmarks: mapToLandmarks(newLandmarks)
                }
            })
        }, [preferences, updatePreferences])
    )

    const renameLandmark = useCallback((fiberId: string, channel: number, name: string) => {
        setLandmarks(prev => {
            const next = new Map(prev)
            const key = landmarkKey(fiberId, channel)
            const existing = next.get(key)

            if (name.trim()) {
                next.set(key, {
                    name: name.trim(),
                    favorite: existing?.favorite ?? false
                })
            } else {
                next.delete(key)
            }
            saveToServer(next)
            return next
        })
    }, [saveToServer])

    const toggleLandmarkFavorite = useCallback((fiberId: string, channel: number) => {
        setLandmarks(prev => {
            const next = new Map(prev)
            const key = landmarkKey(fiberId, channel)
            const existing = next.get(key)

            if (existing) {
                next.set(key, {
                    ...existing,
                    favorite: !existing.favorite
                })
                saveToServer(next)
            }
            return next
        })
    }, [saveToServer])

    const deleteLandmark = useCallback((fiberId: string, channel: number) => {
        setLandmarks(prev => {
            const next = new Map(prev)
            next.delete(landmarkKey(fiberId, channel))
            saveToServer(next)
            return next
        })
    }, [saveToServer])

    const getLandmarkName = useCallback((fiberId: string, channel: number): string | null => {
        return landmarks.get(landmarkKey(fiberId, channel))?.name ?? null
    }, [landmarks])

    const isLandmarkFavorite = useCallback((fiberId: string, channel: number): boolean => {
        return landmarks.get(landmarkKey(fiberId, channel))?.favorite ?? false
    }, [landmarks])

    return (
        <LandmarkDataContext.Provider value={{
            landmarks,
            renameLandmark,
            toggleLandmarkFavorite,
            deleteLandmark,
            getLandmarkName,
            isLandmarkFavorite
        }}>
            {children}
        </LandmarkDataContext.Provider>
    )
}
