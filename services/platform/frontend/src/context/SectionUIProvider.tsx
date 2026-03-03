import { useState, useCallback, type ReactNode } from 'react'
import type { PendingSectionPoint, DraggingEndpoint } from '@/types/section'
import { SectionUIContext } from './SectionUIContext'

/**
 * Provider for ephemeral section interaction state.
 *
 * None of this state is persisted — it resets on page reload.
 * Separated from SectionDataProvider so that hover/drag/creation-mode
 * changes don't re-render consumers who only read section data or
 * layer visibility.
 */
export function SectionUIProvider({ children }: { children: ReactNode }) {
    const [pendingPoint, setPendingPoint] = useState<PendingSectionPoint>(null)
    const [showNamingDialog, setShowNamingDialog] = useState(false)
    const [pendingSection, setPendingSection] = useState<{ fiberId: string; startChannel: number; endChannel: number } | null>(null)
    const [hoveredSectionId, setHoveredSectionId] = useState<string | null>(null)
    const [draggingEndpoint, setDraggingEndpoint] = useState<DraggingEndpoint>(null)
    const [sectionCreationMode, setSectionCreationMode] = useState(false)
    const [previewChannel, setPreviewChannel] = useState<number | null>(null)

    const openNamingDialog = useCallback((fiberId: string, startChannel: number, endChannel: number) => {
        setPendingSection({ fiberId, startChannel, endChannel })
        setShowNamingDialog(true)
    }, [])

    const closeNamingDialog = useCallback(() => {
        setShowNamingDialog(false)
        setPendingSection(null)
    }, [])

    return (
        <SectionUIContext.Provider value={{
            pendingPoint,
            setPendingPoint,
            showNamingDialog,
            pendingSection,
            openNamingDialog,
            closeNamingDialog,
            hoveredSectionId,
            setHoveredSectionId,
            draggingEndpoint,
            setDraggingEndpoint,
            sectionCreationMode,
            setSectionCreationMode,
            previewChannel,
            setPreviewChannel,
        }}>
            {children}
        </SectionUIContext.Provider>
    )
}
