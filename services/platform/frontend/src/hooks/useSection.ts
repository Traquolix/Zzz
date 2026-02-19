import { useContext, useCallback } from 'react'
import { SectionDataContext } from '@/context/SectionContext'
import { useMapSelection } from './useMapSelection'

/**
 * Combined hook for section data and selection.
 * Provides backward-compatible API while using unified selection.
 */
export function useSection() {
    const dataContext = useContext(SectionDataContext)
    if (!dataContext) {
        throw new Error('useSection must be used within SectionDataProvider')
    }

    const { selectedSection, selectSection } = useMapSelection()

    // Wrap createSection to auto-select the new section
    const createSectionAndSelect = useCallback((
        fiberId: string,
        startChannel: number,
        endChannel: number,
        name: string,
        color?: string
    ) => {
        const newSection = dataContext.createSection(fiberId, startChannel, endChannel, name, color)
        selectSection(newSection)
    }, [dataContext, selectSection])

    // Wrap deleteSection to clear selection if needed
    const deleteSectionAndClearSelection = useCallback((sectionId: string) => {
        dataContext.deleteSection(sectionId)
        if (selectedSection?.sectionId === sectionId) {
            selectSection(null)
        }
    }, [dataContext, selectedSection, selectSection])

    // Wrap updateSectionBounds to update selection with new ID
    const updateSectionBoundsAndSelection = useCallback((
        sectionId: string,
        startChannel: number,
        endChannel: number
    ) => {
        const newSection = dataContext.updateSectionBounds(sectionId, startChannel, endChannel)
        if (newSection && selectedSection?.sectionId === sectionId) {
            selectSection(newSection)
        }
    }, [dataContext, selectedSection, selectSection])

    return {
        // Selection (from MapSelectionContext)
        selectedSection,
        selectSection,

        // Data (from SectionDataContext)
        sections: dataContext.sections,
        createSection: createSectionAndSelect,
        renameSection: dataContext.renameSection,
        deleteSection: deleteSectionAndClearSelection,
        updateSectionBounds: updateSectionBoundsAndSelection,
        toggleSectionFavorite: dataContext.toggleSectionFavorite,

        // UI state (from SectionDataContext)
        pendingPoint: dataContext.pendingPoint,
        setPendingPoint: dataContext.setPendingPoint,
        showNamingDialog: dataContext.showNamingDialog,
        pendingSection: dataContext.pendingSection,
        openNamingDialog: dataContext.openNamingDialog,
        closeNamingDialog: dataContext.closeNamingDialog,
        hoveredSectionId: dataContext.hoveredSectionId,
        setHoveredSectionId: dataContext.setHoveredSectionId,
        draggingEndpoint: dataContext.draggingEndpoint,
        setDraggingEndpoint: dataContext.setDraggingEndpoint,
        layerVisibility: dataContext.layerVisibility,
        setLayerVisibility: dataContext.setLayerVisibility,
        sectionCreationMode: dataContext.sectionCreationMode,
        setSectionCreationMode: dataContext.setSectionCreationMode,
        previewChannel: dataContext.previewChannel,
        setPreviewChannel: dataContext.setPreviewChannel
    }
}
