import { useContext } from 'react'
import { LandmarkDataContext } from '@/context/LandmarkSelectionContext'
import { useMapSelection } from './useMapSelection'

/**
 * Combined hook for landmark data and selection.
 * Provides backward-compatible API while using unified selection.
 */
export function useLandmarkSelection() {
    const dataContext = useContext(LandmarkDataContext)
    if (!dataContext) {
        throw new Error('useLandmarkSelection must be used within LandmarkDataProvider')
    }

    const { selectedLandmark, selectLandmark } = useMapSelection()

    return {
        // Selection (from MapSelectionContext)
        selectedLandmark,
        selectLandmark,

        // Data (from LandmarkDataContext)
        landmarks: dataContext.landmarks,
        renameLandmark: dataContext.renameLandmark,
        toggleLandmarkFavorite: dataContext.toggleLandmarkFavorite,
        deleteLandmark: dataContext.deleteLandmark,
        getLandmarkName: dataContext.getLandmarkName,
        isLandmarkFavorite: dataContext.isLandmarkFavorite
    }
}
