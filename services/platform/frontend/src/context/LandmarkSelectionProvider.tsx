import { useCallback, useMemo, type ReactNode } from 'react'
import { LandmarkDataContext, type LandmarkEntry } from './LandmarkSelectionContext'
import { usePreferenceMap } from '@/hooks/usePreferenceMap'
import type { StoredLandmark, UserPreferences } from '@/types/user'

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

const preferenceConfig = {
    load: (prefs: UserPreferences) => {
        const saved = prefs?.map?.landmarks
        if (!saved?.length) return null
        return landmarksToMap(saved)
    },
    save: (map: Map<string, LandmarkEntry>, currentPrefs: UserPreferences | null) => ({
        map: {
            ...currentPrefs?.map,
            landmarks: mapToLandmarks(map),
        },
    }),
}

/**
 * Provider for landmark data (names, favorites).
 * Selection state is managed by MapSelectionProvider.
 */
export function LandmarkDataProvider({ children }: { children: ReactNode }) {
    // eslint-disable-next-line react-hooks/exhaustive-deps
    const config = useMemo(() => preferenceConfig, [])
    const { map: landmarks, setMap: setLandmarks, scheduleSave } = usePreferenceMap(config)

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
            scheduleSave(next)
            return next
        })
    }, [setLandmarks, scheduleSave])

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
                scheduleSave(next)
            }
            return next
        })
    }, [setLandmarks, scheduleSave])

    const deleteLandmark = useCallback((fiberId: string, channel: number) => {
        setLandmarks(prev => {
            const next = new Map(prev)
            next.delete(landmarkKey(fiberId, channel))
            scheduleSave(next)
            return next
        })
    }, [setLandmarks, scheduleSave])

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
