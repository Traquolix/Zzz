import { createContext } from 'react'

export type LandmarkEntry = {
    name: string
    favorite: boolean
}

/**
 * Context for landmark data (names, favorites).
 * Selection state is managed by MapSelectionContext.
 */
export type LandmarkDataContextType = {
    landmarks: Map<string, LandmarkEntry>
    renameLandmark: (fiberId: string, channel: number, name: string) => void
    toggleLandmarkFavorite: (fiberId: string, channel: number) => void
    deleteLandmark: (fiberId: string, channel: number) => void
    getLandmarkName: (fiberId: string, channel: number) => string | null
    isLandmarkFavorite: (fiberId: string, channel: number) => boolean
}

export const LandmarkDataContext = createContext<LandmarkDataContextType | null>(null)
