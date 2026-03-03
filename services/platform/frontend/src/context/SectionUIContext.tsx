import { createContext } from 'react'
import type { PendingSectionPoint, DraggingEndpoint } from '@/types/section'

/**
 * Context for ephemeral section UI state.
 *
 * Separated from SectionDataContext to prevent re-renders in
 * data-only consumers (e.g., useSectionStats) when transient
 * UI state like hover or drag changes.
 */
export type SectionUIContextType = {
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

    // Section creation mode (triggered by button instead of Ctrl+Click)
    sectionCreationMode: boolean
    setSectionCreationMode: (mode: boolean) => void

    // Preview channel during section creation (for UI feedback)
    previewChannel: number | null
    setPreviewChannel: (channel: number | null) => void
}

export const SectionUIContext = createContext<SectionUIContextType | null>(null)
