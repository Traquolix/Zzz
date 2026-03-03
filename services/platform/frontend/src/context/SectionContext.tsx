import { createContext } from 'react'
import type { FiberSection, LayerVisibility, SelectedSection } from '@/types/section'

/**
 * Context for persistent section data and layer visibility.
 *
 * Ephemeral UI state (hover, drag, creation mode) lives in SectionUIContext.
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

    // Layer visibility
    layerVisibility: LayerVisibility
    setLayerVisibility: (visibility: LayerVisibility) => void
}

export const SectionDataContext = createContext<SectionDataContextType | null>(null)
