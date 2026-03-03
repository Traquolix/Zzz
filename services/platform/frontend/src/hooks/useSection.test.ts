import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import type { SelectedSection } from '@/types/section'

// Mock the context modules — NOT react.useContext
vi.mock('@/context/SectionContext', () => ({
    SectionDataContext: { _currentValue: null },
}))
vi.mock('@/context/SectionUIContext', () => ({
    SectionUIContext: { _currentValue: null },
}))
vi.mock('./useMapSelection')

import { useSection } from './useSection'
import { useMapSelection } from './useMapSelection'
import { SectionDataContext } from '@/context/SectionContext'
import { SectionUIContext } from '@/context/SectionUIContext'

const mockSelectSection = vi.fn()

const mockSection: SelectedSection = {
    sectionId: 'section-1',
    fiberId: 'fiber-1',
    startChannel: 0,
    endChannel: 10,
    name: 'Test Section',
} as any

const mockSection2: SelectedSection = {
    sectionId: 'section-2',
    fiberId: 'fiber-2',
    startChannel: 20,
    endChannel: 30,
    name: 'Section 2',
} as any

const mockDataContext = {
    sections: new Map([
        ['section-1', { id: 'section-1', name: 'Test Section' }],
        ['section-2', { id: 'section-2', name: 'Section 2' }],
    ]),
    createSection: vi.fn(() => mockSection),
    renameSection: vi.fn(),
    deleteSection: vi.fn(),
    updateSectionBounds: vi.fn(() => mockSection),
    toggleSectionFavorite: vi.fn(),
    layerVisibility: { sections: true },
    setLayerVisibility: vi.fn(),
}

const mockUIContext = {
    pendingPoint: null,
    setPendingPoint: vi.fn(),
    showNamingDialog: false,
    pendingSection: null,
    openNamingDialog: vi.fn(),
    closeNamingDialog: vi.fn(),
    hoveredSectionId: null,
    setHoveredSectionId: vi.fn(),
    draggingEndpoint: null,
    setDraggingEndpoint: vi.fn(),
    sectionCreationMode: false,
    setSectionCreationMode: vi.fn(),
    previewChannel: null,
    setPreviewChannel: vi.fn(),
}

describe('useSection', () => {
    beforeEach(() => {
        vi.clearAllMocks()
        mockSelectSection.mockClear()

        vi.mocked(useMapSelection).mockReturnValue({
            selectedSection: mockSection,
            selectSection: mockSelectSection,
            selectedLandmark: null,
            selectLandmark: vi.fn(),
            selectedVehicle: null,
            selectVehicle: vi.fn(),
            selectedIncident: null,
            selectIncident: vi.fn(),
            selectedInfrastructure: null,
            selectInfrastructure: vi.fn(),
            selection: { type: 'section', data: mockSection } as any,
            select: vi.fn(),
        } as any)

        // Set context values directly on the React internals
        ;(SectionDataContext as any)._currentValue = mockDataContext
        ;(SectionUIContext as any)._currentValue = mockUIContext
    })

    it('returns sections from data context', () => {
        const { result } = renderHook(() => useSection())
        expect(result.current.sections).toBe(mockDataContext.sections)
    })

    it('returns selected section from map selection hook', () => {
        const { result } = renderHook(() => useSection())
        expect(result.current.selectedSection).toBe(mockSection)
    })

    it('delegates selectSection to useMapSelection', () => {
        const { result } = renderHook(() => useSection())
        act(() => {
            result.current.selectSection(mockSection2)
        })
        expect(mockSelectSection).toHaveBeenCalledWith(mockSection2)
    })

    it('createSection calls context and auto-selects', () => {
        const { result } = renderHook(() => useSection())
        act(() => {
            result.current.createSection('fiber-1', 0, 10, 'New Section')
        })
        expect(mockDataContext.createSection).toHaveBeenCalledWith('fiber-1', 0, 10, 'New Section', undefined)
        expect(mockSelectSection).toHaveBeenCalledWith(mockSection)
    })

    it('deleteSection calls context and clears selection when deleting selected', () => {
        const { result } = renderHook(() => useSection())
        act(() => {
            result.current.deleteSection('section-1')
        })
        expect(mockDataContext.deleteSection).toHaveBeenCalledWith('section-1')
        expect(mockSelectSection).toHaveBeenCalledWith(null)
    })

    it('deleteSection does not clear selection when deleting non-selected', () => {
        const { result } = renderHook(() => useSection())
        act(() => {
            result.current.deleteSection('section-99')
        })
        expect(mockDataContext.deleteSection).toHaveBeenCalledWith('section-99')
        expect(mockSelectSection).not.toHaveBeenCalledWith(null)
    })

    it('updateSectionBounds calls context and updates selection', () => {
        const { result } = renderHook(() => useSection())
        act(() => {
            result.current.updateSectionBounds('section-1', 5, 15)
        })
        expect(mockDataContext.updateSectionBounds).toHaveBeenCalledWith('section-1', 5, 15)
        expect(mockSelectSection).toHaveBeenCalledWith(mockSection)
    })

    it('returns all data context methods', () => {
        const { result } = renderHook(() => useSection())
        expect(result.current.renameSection).toBe(mockDataContext.renameSection)
        expect(result.current.toggleSectionFavorite).toBe(mockDataContext.toggleSectionFavorite)
        expect(result.current.layerVisibility).toBe(mockDataContext.layerVisibility)
        expect(result.current.setLayerVisibility).toBe(mockDataContext.setLayerVisibility)
    })

    it('returns all UI context state and methods', () => {
        const { result } = renderHook(() => useSection())
        expect(result.current.pendingPoint).toBe(mockUIContext.pendingPoint)
        expect(result.current.setPendingPoint).toBe(mockUIContext.setPendingPoint)
        expect(result.current.showNamingDialog).toBe(mockUIContext.showNamingDialog)
        expect(result.current.pendingSection).toBe(mockUIContext.pendingSection)
        expect(result.current.openNamingDialog).toBe(mockUIContext.openNamingDialog)
        expect(result.current.closeNamingDialog).toBe(mockUIContext.closeNamingDialog)
        expect(result.current.hoveredSectionId).toBe(mockUIContext.hoveredSectionId)
        expect(result.current.setHoveredSectionId).toBe(mockUIContext.setHoveredSectionId)
        expect(result.current.draggingEndpoint).toBe(mockUIContext.draggingEndpoint)
        expect(result.current.setDraggingEndpoint).toBe(mockUIContext.setDraggingEndpoint)
        expect(result.current.sectionCreationMode).toBe(mockUIContext.sectionCreationMode)
        expect(result.current.setSectionCreationMode).toBe(mockUIContext.setSectionCreationMode)
        expect(result.current.previewChannel).toBe(mockUIContext.previewChannel)
        expect(result.current.setPreviewChannel).toBe(mockUIContext.setPreviewChannel)
    })

})
