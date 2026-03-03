import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook } from '@testing-library/react'
import { createContext, type ReactNode } from 'react'
import type { SelectedLandmark } from '@/types/selection'

// Mock useMapSelection
vi.mock('./useMapSelection', () => ({
    useMapSelection: vi.fn(),
}))

// Mock LandmarkDataContext
vi.mock('@/context/LandmarkSelectionContext', () => ({
    LandmarkDataContext: createContext<any>(null),
}))

import { useMapSelection } from './useMapSelection'
import { useLandmarkSelection } from './useLandmarkSelection'
import { LandmarkDataContext } from '@/context/LandmarkSelectionContext'

describe('useLandmarkSelection', () => {
    beforeEach(() => {
        vi.clearAllMocks()
    })

    it('throws error when used outside LandmarkDataProvider', () => {
        vi.mocked(useMapSelection).mockReturnValue({
            selectedLandmark: null,
            selectLandmark: vi.fn(),
        } as any)

        const spy = vi.spyOn(console, 'error').mockImplementation(() => {})

        expect(() => {
            renderHook(() => useLandmarkSelection())
        }).toThrow('useLandmarkSelection must be used within LandmarkDataProvider')

        spy.mockRestore()
    })

    it('returns landmarks from context', () => {
        const mockLandmarks = new Map([
            ['lm-1', { id: 'lm-1', name: 'Landmark 1', fiberId: 'fiber-1', channel: 5, favorite: false }],
            ['lm-2', { id: 'lm-2', name: 'Landmark 2', fiberId: 'fiber-2', channel: 10, favorite: false }],
        ])

        const mockDataContext = {
            landmarks: mockLandmarks,
            renameLandmark: vi.fn(),
            toggleLandmarkFavorite: vi.fn(),
            deleteLandmark: vi.fn(),
            getLandmarkName: vi.fn(),
            isLandmarkFavorite: vi.fn(),
        }

        const mockMapSelection = {
            selectedLandmark: null,
            selectLandmark: vi.fn(),
        }

        vi.mocked(useMapSelection).mockReturnValue(mockMapSelection as any)

        const wrapper = ({ children }: { children: ReactNode }) => (
            <LandmarkDataContext.Provider value={mockDataContext}>
                {children}
            </LandmarkDataContext.Provider>
        )

        const { result } = renderHook(() => useLandmarkSelection(), { wrapper })

        expect(result.current.landmarks).toEqual(mockLandmarks)
    })

    it('returns selected landmark from map selection context', () => {
        const selectedLandmark: SelectedLandmark = {
            fiberId: 'fiber-1',
            channel: 5,
            lng: 10.5,
            lat: 20.3,
        }

        const mockDataContext = {
            landmarks: new Map(),
            renameLandmark: vi.fn(),
            toggleLandmarkFavorite: vi.fn(),
            deleteLandmark: vi.fn(),
            getLandmarkName: vi.fn(),
            isLandmarkFavorite: vi.fn(),
        }

        const mockMapSelection = {
            selectedLandmark,
            selectLandmark: vi.fn(),
        }

        vi.mocked(useMapSelection).mockReturnValue(mockMapSelection as any)

        const wrapper = ({ children }: { children: ReactNode }) => (
            <LandmarkDataContext.Provider value={mockDataContext}>
                {children}
            </LandmarkDataContext.Provider>
        )

        const { result } = renderHook(() => useLandmarkSelection(), { wrapper })

        expect(result.current.selectedLandmark).toEqual(selectedLandmark)
    })

    it('returns selectLandmark function from map selection context', () => {
        const mockSelectLandmark = vi.fn()

        const mockDataContext = {
            landmarks: new Map(),
            renameLandmark: vi.fn(),
            toggleLandmarkFavorite: vi.fn(),
            deleteLandmark: vi.fn(),
            getLandmarkName: vi.fn(),
            isLandmarkFavorite: vi.fn(),
        }

        const mockMapSelection = {
            selectedLandmark: null,
            selectLandmark: mockSelectLandmark,
        }

        vi.mocked(useMapSelection).mockReturnValue(mockMapSelection as any)

        const wrapper = ({ children }: { children: ReactNode }) => (
            <LandmarkDataContext.Provider value={mockDataContext}>
                {children}
            </LandmarkDataContext.Provider>
        )

        const { result } = renderHook(() => useLandmarkSelection(), { wrapper })

        expect(result.current.selectLandmark).toBe(mockSelectLandmark)
    })

    it('returns data methods from landmark context', () => {
        const mockRenameLandmark = vi.fn()
        const mockToggleLandmarkFavorite = vi.fn()
        const mockDeleteLandmark = vi.fn()
        const mockGetLandmarkName = vi.fn(() => 'Landmark Name')
        const mockIsLandmarkFavorite = vi.fn(() => true)

        const mockDataContext = {
            landmarks: new Map([['lm-1', { id: 'lm-1', name: 'Landmark 1', fiberId: 'fiber-1', channel: 1, favorite: false }]]),
            renameLandmark: mockRenameLandmark,
            toggleLandmarkFavorite: mockToggleLandmarkFavorite,
            deleteLandmark: mockDeleteLandmark,
            getLandmarkName: mockGetLandmarkName,
            isLandmarkFavorite: mockIsLandmarkFavorite,
        }

        const mockMapSelection = {
            selectedLandmark: null,
            selectLandmark: vi.fn(),
        }

        vi.mocked(useMapSelection).mockReturnValue(mockMapSelection as any)

        const wrapper = ({ children }: { children: ReactNode }) => (
            <LandmarkDataContext.Provider value={mockDataContext}>
                {children}
            </LandmarkDataContext.Provider>
        )

        const { result } = renderHook(() => useLandmarkSelection(), { wrapper })

        expect(result.current.renameLandmark).toBe(mockRenameLandmark)
        expect(result.current.toggleLandmarkFavorite).toBe(mockToggleLandmarkFavorite)
        expect(result.current.deleteLandmark).toBe(mockDeleteLandmark)
        expect(result.current.getLandmarkName).toBe(mockGetLandmarkName)
        expect(result.current.isLandmarkFavorite).toBe(mockIsLandmarkFavorite)
    })

    it('combines selection and data methods correctly', () => {
        const selectedLandmark: SelectedLandmark = {
            fiberId: 'fiber-1',
            channel: 5,
            lng: 10.5,
            lat: 20.3,
        }

        const mockLandmarks = new Map([
            ['lm-1', { id: 'lm-1', name: 'Landmark 1', fiberId: 'fiber-1', channel: 1, favorite: false }],
            ['lm-2', { id: 'lm-2', name: 'Landmark 2', fiberId: 'fiber-2', channel: 2, favorite: false }],
        ])

        const mockSelectLandmark = vi.fn()
        const mockRenameLandmark = vi.fn()

        const mockDataContext = {
            landmarks: mockLandmarks,
            renameLandmark: mockRenameLandmark,
            toggleLandmarkFavorite: vi.fn(),
            deleteLandmark: vi.fn(),
            getLandmarkName: vi.fn(),
            isLandmarkFavorite: vi.fn(),
        }

        const mockMapSelection = {
            selectedLandmark,
            selectLandmark: mockSelectLandmark,
        }

        vi.mocked(useMapSelection).mockReturnValue(mockMapSelection as any)

        const wrapper = ({ children }: { children: ReactNode }) => (
            <LandmarkDataContext.Provider value={mockDataContext}>
                {children}
            </LandmarkDataContext.Provider>
        )

        const { result } = renderHook(() => useLandmarkSelection(), { wrapper })

        expect(result.current.selectedLandmark).toEqual(selectedLandmark)
        expect(result.current.selectLandmark).toBe(mockSelectLandmark)
        expect(result.current.landmarks).toEqual(mockLandmarks)
        expect(result.current.renameLandmark).toBe(mockRenameLandmark)
    })

    it('handles null selected landmark', () => {
        const mockDataContext = {
            landmarks: new Map([['lm-1', { id: 'lm-1', name: 'Landmark 1', fiberId: 'fiber-1', channel: 1, favorite: false }]]),
            renameLandmark: vi.fn(),
            toggleLandmarkFavorite: vi.fn(),
            deleteLandmark: vi.fn(),
            getLandmarkName: vi.fn(),
            isLandmarkFavorite: vi.fn(),
        }

        const mockMapSelection = {
            selectedLandmark: null,
            selectLandmark: vi.fn(),
        }

        vi.mocked(useMapSelection).mockReturnValue(mockMapSelection as any)

        const wrapper = ({ children }: { children: ReactNode }) => (
            <LandmarkDataContext.Provider value={mockDataContext}>
                {children}
            </LandmarkDataContext.Provider>
        )

        const { result } = renderHook(() => useLandmarkSelection(), { wrapper })

        expect(result.current.selectedLandmark).toBeNull()
        expect(result.current.landmarks.size).toBe(1)
    })
})
