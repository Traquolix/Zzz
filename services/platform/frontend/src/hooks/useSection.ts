import { useContext, useCallback } from 'react'
import { SectionDataContext } from '@/context/SectionContext'
import { SectionUIContext } from '@/context/SectionUIContext'
import { useMapSelection } from './useMapSelection'

/**
 * Combined hook for section data, UI state, and selection.
 *
 * Merges three contexts into a single backward-compatible API:
 * - SectionDataContext: persistent CRUD + layer visibility
 * - SectionUIContext: ephemeral interaction state
 * - MapSelectionContext: selected section
 */
export function useSection() {
    const dataContext = useContext(SectionDataContext)
    if (!dataContext) {
        throw new Error('useSection must be used within SectionDataProvider')
    }

    const uiContext = useContext(SectionUIContext)
    if (!uiContext) {
        throw new Error('useSection must be used within SectionUIProvider')
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

        // Layer visibility (from SectionDataContext — persisted)
        layerVisibility: dataContext.layerVisibility,
        setLayerVisibility: dataContext.setLayerVisibility,

        // UI state (from SectionUIContext — ephemeral)
        pendingPoint: uiContext.pendingPoint,
        setPendingPoint: uiContext.setPendingPoint,
        showNamingDialog: uiContext.showNamingDialog,
        pendingSection: uiContext.pendingSection,
        openNamingDialog: uiContext.openNamingDialog,
        closeNamingDialog: uiContext.closeNamingDialog,
        hoveredSectionId: uiContext.hoveredSectionId,
        setHoveredSectionId: uiContext.setHoveredSectionId,
        draggingEndpoint: uiContext.draggingEndpoint,
        setDraggingEndpoint: uiContext.setDraggingEndpoint,
        sectionCreationMode: uiContext.sectionCreationMode,
        setSectionCreationMode: uiContext.setSectionCreationMode,
        previewChannel: uiContext.previewChannel,
        setPreviewChannel: uiContext.setPreviewChannel,
    }
}
