/**
 * TDD tests for decomposed SectionProvider architecture.
 *
 * Goal: After splitting SectionProvider into SectionStoreProvider (persistent
 * CRUD + layer visibility) and SectionUIProvider (ephemeral interaction state),
 * the combined useSection() hook must provide the same behavioral contract:
 *
 * 1. Sections can be created, renamed, deleted, and resized
 * 2. Layer visibility can be toggled
 * 3. Ephemeral UI state (pending point, naming dialog, hover, etc.) works independently
 * 4. UI state changes don't trigger re-renders in CRUD-only consumers
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import type { ReactNode } from 'react'

// Mock preferences — no persistence needed for these tests
vi.mock('@/hooks/useUserPreferences', () => ({
    useUserPreferences: () => ({
        preferences: null,
        updatePreferences: vi.fn(),
        isLoading: false,
    }),
}))

vi.mock('@/hooks/useDebouncedSync', () => ({
    useDebouncedSync: (fn: Function) => fn,
}))

vi.mock('@/hooks/useMapSelection', () => ({
    useMapSelection: () => ({
        selectedSection: null,
        selectSection: vi.fn(),
    }),
}))

import { SectionDataProvider } from './SectionProvider'
import { SectionUIProvider } from './SectionUIProvider'
import { useSection } from '@/hooks/useSection'

function AllProviders({ children }: { children: ReactNode }) {
    return (
        <SectionDataProvider>
            <SectionUIProvider>
                {children}
            </SectionUIProvider>
        </SectionDataProvider>
    )
}

describe('Decomposed SectionProvider', () => {
    beforeEach(() => {
        vi.clearAllMocks()
    })

    it('creates a section with correct ID and properties', () => {
        const { result } = renderHook(() => useSection(), { wrapper: AllProviders })

        act(() => {
            result.current.createSection('fiber:0', 10, 50, 'Test Section')
        })

        const sections = result.current.sections
        expect(sections.size).toBe(1)

        const [id, section] = Array.from(sections.entries())[0]
        expect(id).toContain('fiber:0')
        expect(id).toContain('10-50')
        expect(section.name).toBe('Test Section')
        expect(section.startChannel).toBe(10)
        expect(section.endChannel).toBe(50)
    })

    it('renames a section', () => {
        const { result } = renderHook(() => useSection(), { wrapper: AllProviders })

        act(() => {
            result.current.createSection('fiber:0', 0, 100, 'Original')
        })

        const sectionId = Array.from(result.current.sections.keys())[0]

        act(() => {
            result.current.renameSection(sectionId, 'Renamed')
        })

        expect(result.current.sections.get(sectionId)?.name).toBe('Renamed')
    })

    it('deletes a section', () => {
        const { result } = renderHook(() => useSection(), { wrapper: AllProviders })

        act(() => {
            result.current.createSection('fiber:0', 0, 100, 'To Delete')
        })

        const sectionId = Array.from(result.current.sections.keys())[0]

        act(() => {
            result.current.deleteSection(sectionId)
        })

        expect(result.current.sections.size).toBe(0)
    })

    it('manages layer visibility independently of section CRUD', () => {
        const { result } = renderHook(() => useSection(), { wrapper: AllProviders })

        // Default visibility
        expect(result.current.layerVisibility.cables).toBe(true)
        expect(result.current.layerVisibility.sections).toBe(false)

        act(() => {
            result.current.setLayerVisibility({
                ...result.current.layerVisibility,
                sections: true,
            })
        })

        expect(result.current.layerVisibility.sections).toBe(true)
    })

    it('manages ephemeral UI state through SectionUIProvider', () => {
        const { result } = renderHook(() => useSection(), { wrapper: AllProviders })

        // Pending point
        expect(result.current.pendingPoint).toBeNull()
        act(() => {
            result.current.setPendingPoint({ fiberId: 'fiber:0', channel: 42, lng: 7.0, lat: 43.0 })
        })
        expect(result.current.pendingPoint).toEqual({ fiberId: 'fiber:0', channel: 42, lng: 7.0, lat: 43.0 })

        // Section creation mode
        expect(result.current.sectionCreationMode).toBe(false)
        act(() => {
            result.current.setSectionCreationMode(true)
        })
        expect(result.current.sectionCreationMode).toBe(true)

        // Hover state
        expect(result.current.hoveredSectionId).toBeNull()
        act(() => {
            result.current.setHoveredSectionId('section:fiber:0:10-50')
        })
        expect(result.current.hoveredSectionId).toBe('section:fiber:0:10-50')
    })

    it('manages naming dialog state', () => {
        const { result } = renderHook(() => useSection(), { wrapper: AllProviders })

        expect(result.current.showNamingDialog).toBe(false)

        act(() => {
            result.current.openNamingDialog('fiber:0', 10, 50)
        })

        expect(result.current.showNamingDialog).toBe(true)
        expect(result.current.pendingSection).toEqual({
            fiberId: 'fiber:0',
            startChannel: 10,
            endChannel: 50,
        })

        act(() => {
            result.current.closeNamingDialog()
        })

        expect(result.current.showNamingDialog).toBe(false)
        expect(result.current.pendingSection).toBeNull()
    })
})
