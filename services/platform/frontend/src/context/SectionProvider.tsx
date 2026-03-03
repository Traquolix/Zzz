import { useState, useCallback, useEffect, useRef, type ReactNode } from 'react'
import type { FiberSection, LayerVisibility, SelectedSection } from '@/types/section'
import { SectionDataContext } from './SectionContext'
import { useUserPreferences } from '@/hooks/useUserPreferences'
import { useDebouncedSync } from '@/hooks/useDebouncedSync'

function generateSectionId(fiberId: string, startChannel: number, endChannel: number): string {
    return `section:${fiberId}:${startChannel}-${endChannel}`
}

const DEFAULT_LAYER_VISIBILITY: LayerVisibility = {
    cables: true,
    fibers: true,
    vehicles: true,
    heatmap: true,
    landmarks: false,
    sections: false,
    detections: true,
    incidents: true,
    infrastructure: true
}

/**
 * Provider for persistent section data and layer visibility.
 *
 * Manages the sections Map, CRUD operations, and layer visibility
 * state — all of which are synced to user preferences on the server.
 *
 * Ephemeral UI state (hover, drag, pending points, naming dialog)
 * lives in SectionUIProvider.
 */
export function SectionDataProvider({ children }: { children: ReactNode }) {
    const { preferences, updatePreferences, isLoading: prefsLoading } = useUserPreferences()
    const initializedRef = useRef(false)
    const preferencesRef = useRef(preferences)
    preferencesRef.current = preferences

    const [sections, setSections] = useState<Map<string, FiberSection>>(new Map())
    const [layerVisibility, setLayerVisibilityState] = useState<LayerVisibility>(DEFAULT_LAYER_VISIBILITY)
    const sectionsRef = useRef(sections)
    sectionsRef.current = sections
    const layerVisibilityRef = useRef(layerVisibility)
    layerVisibilityRef.current = layerVisibility

    // Initialize from server preferences (only once when preferences first load)
    useEffect(() => {
        if (prefsLoading || initializedRef.current) return

        initializedRef.current = true
        const savedSections = preferences?.map?.sections
        const savedVisibility = preferences?.map?.layerVisibility

        if (savedSections && savedSections.length > 0) {
            const sectionsMap = new Map(savedSections.map(s => [s.id, s]))
            setSections(sectionsMap)
        }

        if (savedVisibility) {
            setLayerVisibilityState({ ...DEFAULT_LAYER_VISIBILITY, ...savedVisibility })
        }
    }, [prefsLoading, preferences])

    // Debounced save to server — use ref to avoid stale closure over preferences
    const saveToServer = useDebouncedSync(
        useCallback((newSections: Map<string, FiberSection>, newVisibility: LayerVisibility) => {
            const current = preferencesRef.current
            updatePreferences({
                ...current,
                map: {
                    ...current?.map,
                    sections: Array.from(newSections.values()),
                    layerVisibility: newVisibility
                }
            })
        }, [updatePreferences])
    )

    // Returns the created section for caller to handle selection
    const createSection = useCallback((
        fiberId: string,
        startChannel: number,
        endChannel: number,
        name: string,
        color?: string
    ): SelectedSection => {
        const id = generateSectionId(fiberId, startChannel, endChannel)
        const section: FiberSection = {
            id,
            fiberId,
            startChannel,
            endChannel,
            name: name.trim(),
            color
        }
        setSections(prev => {
            const next = new Map(prev)
            next.set(id, section)
            saveToServer(next, layerVisibilityRef.current)
            return next
        })
        return { sectionId: id, fiberId }
    }, [saveToServer])

    const renameSection = useCallback((sectionId: string, name: string) => {
        setSections(prev => {
            const section = prev.get(sectionId)
            if (!section) return prev
            const next = new Map(prev)
            next.set(sectionId, { ...section, name: name.trim() })
            saveToServer(next, layerVisibilityRef.current)
            return next
        })
    }, [saveToServer])

    const deleteSection = useCallback((sectionId: string) => {
        setSections(prev => {
            const next = new Map(prev)
            next.delete(sectionId)
            saveToServer(next, layerVisibilityRef.current)
            return next
        })
    }, [saveToServer])

    const toggleSectionFavorite = useCallback((sectionId: string) => {
        setSections(prev => {
            const section = prev.get(sectionId)
            if (!section) return prev
            const next = new Map(prev)
            next.set(sectionId, { ...section, favorite: !section.favorite })
            saveToServer(next, layerVisibilityRef.current)
            return next
        })
    }, [saveToServer])

    // Returns the new section reference if bounds were updated
    const updateSectionBounds = useCallback((
        sectionId: string,
        startChannel: number,
        endChannel: number
    ): SelectedSection | null => {
        let newSection: SelectedSection | null = null

        setSections(prev => {
            const section = prev.get(sectionId)
            if (!section) return prev

            // Generate new ID based on new bounds
            const newId = generateSectionId(section.fiberId, startChannel, endChannel)
            const next = new Map(prev)

            // Remove old entry and add new one with updated bounds
            next.delete(sectionId)
            next.set(newId, {
                ...section,
                id: newId,
                startChannel,
                endChannel
            })

            newSection = { sectionId: newId, fiberId: section.fiberId }
            saveToServer(next, layerVisibilityRef.current)
            return next
        })

        return newSection
    }, [saveToServer])

    const setLayerVisibility = useCallback((visibility: LayerVisibility) => {
        setLayerVisibilityState(visibility)
        saveToServer(sectionsRef.current, visibility)
    }, [saveToServer])

    return (
        <SectionDataContext.Provider value={{
            sections,
            createSection,
            renameSection,
            deleteSection,
            updateSectionBounds,
            toggleSectionFavorite,
            layerVisibility,
            setLayerVisibility,
        }}>
            {children}
        </SectionDataContext.Provider>
    )
}
