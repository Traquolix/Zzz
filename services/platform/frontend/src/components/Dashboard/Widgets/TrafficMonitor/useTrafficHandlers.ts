import { useCallback, useMemo } from 'react'
import { useMapInstance } from '@/hooks/useMapInstance'
import type { SelectedLandmark } from '@/types/selection'
import type { FiberSection } from '@/types/section'
import type { FiberLine } from '@/types/fiber'
import type { LandmarkInfo } from './types'

interface UseTrafficHandlersProps {
    selectedLandmark: SelectedLandmark | null
    sections: Map<string, FiberSection>
    fibers: FiberLine[]
    selectLandmark: (landmark: SelectedLandmark) => void
    selectSection: (arg: { sectionId: string; fiberId: string }) => void
    renameLandmark: (fiberId: string, channel: number, name: string) => void
    toggleLandmarkFavorite: (fiberId: string, channel: number) => void
    deleteLandmark: (fiberId: string, channel: number) => void
}

export function useTrafficHandlers({
    selectedLandmark,
    sections,
    fibers,
    selectLandmark,
    selectSection,
    renameLandmark,
    toggleLandmarkFavorite,
    deleteLandmark,
}: UseTrafficHandlersProps) {
    const { flyToWithLayer, fitBoundsWithLayer, ensureLayerVisible } = useMapInstance()

    const handleLandmarkSelect = useCallback((landmark: LandmarkInfo) => {
        ensureLayerVisible('landmarks')
        selectLandmark({
            fiberId: landmark.fiberId,
            channel: landmark.channel,
            lng: landmark.lng,
            lat: landmark.lat
        })
    }, [ensureLayerVisible, selectLandmark])

    const handleLandmarkFlyTo = useCallback((landmark: LandmarkInfo, e: React.MouseEvent) => {
        e.stopPropagation()
        flyToWithLayer(landmark.lng, landmark.lat, 'landmarks', 16, 3000)
    }, [flyToWithLayer])

    const handleSectionSelect = useCallback((sectionId: string, fiberId: string) => {
        ensureLayerVisible('sections')
        selectSection({ sectionId, fiberId })
    }, [ensureLayerVisible, selectSection])

    const handleSectionFlyTo = useCallback((sectionId: string, e: React.MouseEvent) => {
        e.stopPropagation()
        const section = sections.get(sectionId)
        if (section) {
            const fiber = fibers.find(f => f.id === section.fiberId)
            if (fiber) {
                const startCoord = fiber.coordinates[section.startChannel]
                const endCoord = fiber.coordinates[section.endChannel]
                if (startCoord && endCoord) {
                    fitBoundsWithLayer([startCoord, endCoord], 'sections', 80, 3000)
                }
            }
        }
    }, [sections, fibers, fitBoundsWithLayer])

    const handleSelectedLandmarkRename = useCallback((name: string) => {
        if (selectedLandmark) {
            renameLandmark(selectedLandmark.fiberId, selectedLandmark.channel, name)
        }
    }, [selectedLandmark, renameLandmark])

    const handleSelectedLandmarkFlyTo = useCallback((lng: number, lat: number) => {
        flyToWithLayer(lng, lat, 'landmarks', 16, 3000)
    }, [flyToWithLayer])

    const landmarkActions = useMemo(() => ({
        onSelect: handleLandmarkSelect,
        onFlyTo: handleLandmarkFlyTo,
        onRename: renameLandmark,
        onToggleFavorite: toggleLandmarkFavorite,
        onDelete: deleteLandmark,
    }), [handleLandmarkSelect, handleLandmarkFlyTo, renameLandmark, toggleLandmarkFavorite, deleteLandmark])

    return {
        handleSectionSelect,
        handleSectionFlyTo,
        handleSelectedLandmarkRename,
        handleSelectedLandmarkFlyTo,
        landmarkActions
    }
}
