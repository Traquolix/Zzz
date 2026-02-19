import { createContext } from 'react'
import type { FiberSection, PendingSectionPoint, LayerVisibility, SelectedSection, DraggingEndpoint } from '@/types/section'

/**
 * Context for section data and UI state.
 * Selection state is managed by MapSelectionContext.
 *
 * Note: createSection returns the created section for the caller to handle selection.
 */
export type SectionDataContextType = {
    // Section data
    sections: Map<string, FiberSection>

    // Section CRUD
    createSection: (fiberId: string, startChannel: number, endChannel: number, name: string, color?: string) => SelectedSection
    renameSection: (sectionId: string, name: string) => void
    deleteSection: (sectionId: string) => void
    updateSectionBounds: (sectionId: string, startChannel: number, endChannel: number) => SelectedSection | null
    toggleSectionFavorite: (sectionId: string) => void

    // Pending section creation (Ctrl+Click workflow)
    pendingPoint: PendingSectionPoint
    setPendingPoint: (point: PendingSectionPoint) => void

    // Naming dialog
    showNamingDialog: boolean
    pendingSection: { fiberId: string; startChannel: number; endChannel: number } | null
    openNamingDialog: (fiberId: string, startChannel: number, endChannel: number) => void
    closeNamingDialog: () => void

    // Hover state for highlighting
    hoveredSectionId: string | null
    setHoveredSectionId: (id: string | null) => void

    // Dragging endpoint for resize
    draggingEndpoint: DraggingEndpoint
    setDraggingEndpoint: (endpoint: DraggingEndpoint) => void

    // Layer visibility
    layerVisibility: LayerVisibility
    setLayerVisibility: (visibility: LayerVisibility) => void

    // Section creation mode (triggered by button instead of Ctrl+Click)
    sectionCreationMode: boolean
    setSectionCreationMode: (mode: boolean) => void

    // Preview channel during section creation (for UI feedback)
    previewChannel: number | null
    setPreviewChannel: (channel: number | null) => void
}

export const SectionDataContext = createContext<SectionDataContextType | null>(null)
