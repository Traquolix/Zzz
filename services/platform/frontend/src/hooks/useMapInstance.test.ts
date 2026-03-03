import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import type { LayerVisibility } from '@/types/section'

// Mock context modules and mapbox — NOT react.useContext
vi.mock('@/context/MapInstanceContext', () => ({
    MapInstanceContext: { _currentValue: null },
}))
vi.mock('@/context/SectionContext', () => ({
    SectionDataContext: { _currentValue: null },
}))
vi.mock('@/context/DashboardContext')
vi.mock('mapbox-gl', () => ({
    default: {
        LngLatBounds: class MockLngLatBounds {
            sw: [number, number]
            ne: [number, number]
            constructor(sw: [number, number], ne: [number, number]) {
                this.sw = [...sw]
                this.ne = [...ne]
            }
            extend(coord: [number, number]) {
                this.sw = [Math.min(this.sw[0], coord[0]), Math.min(this.sw[1], coord[1])]
                this.ne = [Math.max(this.ne[0], coord[0]), Math.max(this.ne[1], coord[1])]
                return this
            }
        }
    }
}))

import { useMapInstance } from './useMapInstance'
import { useDashboardState } from '@/context/DashboardContext'
import { MapInstanceContext } from '@/context/MapInstanceContext'
import { SectionDataContext } from '@/context/SectionContext'

const mockFlyTo = vi.fn()
const mockFitBounds = vi.fn()

const mockMapInstance = {
    flyTo: mockFlyTo,
    fitBounds: mockFitBounds,
    getCenter: vi.fn(),
    getZoom: vi.fn(),
} as any

const mockSetLayerVisibility = vi.fn()

describe('useMapInstance', () => {
    beforeEach(() => {
        vi.clearAllMocks()

        vi.mocked(useDashboardState).mockReturnValue({
            hasWidgetType: vi.fn((type) => type === 'map'),
        } as any)

        // Set context values via React internals
        ;(MapInstanceContext as any)._currentValue = {
            map: mockMapInstance,
            ready: true,
            setMapInstance: vi.fn(),
        }
        ;(SectionDataContext as any)._currentValue = {
            sections: new Map(),
            createSection: vi.fn(),
            renameSection: vi.fn(),
            deleteSection: vi.fn(),
            updateSectionBounds: vi.fn(),
            toggleSectionFavorite: vi.fn(),
            layerVisibility: { sections: true, infrastructure: false } as LayerVisibility,
            setLayerVisibility: mockSetLayerVisibility,
        }
    })

    it('returns map instance and ready state', () => {
        const { result } = renderHook(() => useMapInstance())
        expect(result.current.map).toBe(mockMapInstance)
        expect(result.current.ready).toBe(true)
    })

    it('returns null map when not ready', () => {
        ;(MapInstanceContext as any)._currentValue = {
            map: null,
            ready: false,
            setMapInstance: vi.fn(),
        }

        const { result } = renderHook(() => useMapInstance())
        expect(result.current.map).toBeNull()
        expect(result.current.ready).toBe(false)
    })

    it('flyTo calls map.flyTo with correct parameters', () => {
        const { result } = renderHook(() => useMapInstance())
        act(() => {
            result.current.flyTo(10.5, 20.5, 18, 3000)
        })
        expect(mockFlyTo).toHaveBeenCalledWith({
            center: [10.5, 20.5],
            zoom: 18,
            duration: 3000,
        })
    })

    it('flyTo uses default zoom and duration', () => {
        const { result } = renderHook(() => useMapInstance())
        act(() => {
            result.current.flyTo(10.5, 20.5)
        })
        expect(mockFlyTo).toHaveBeenCalledWith({
            center: [10.5, 20.5],
            zoom: 16,
            duration: 2000,
        })
    })

    it('flyTo does nothing when map is null', () => {
        ;(MapInstanceContext as any)._currentValue = {
            map: null,
            ready: false,
            setMapInstance: vi.fn(),
        }

        const { result } = renderHook(() => useMapInstance())
        act(() => {
            result.current.flyTo(10.5, 20.5)
        })
        expect(mockFlyTo).not.toHaveBeenCalled()
    })

    it('fitBounds calls map.fitBounds with computed bounds', () => {
        const coords: [number, number][] = [[10, 20], [15, 25], [12, 22]]

        const { result } = renderHook(() => useMapInstance())
        act(() => {
            result.current.fitBounds(coords, 100, 3000)
        })

        expect(mockFitBounds).toHaveBeenCalled()
        const callArgs = mockFitBounds.mock.calls[0]
        expect(callArgs[1]).toEqual({ padding: 100, duration: 3000 })
    })

    it('fitBounds uses default padding and duration', () => {
        const coords: [number, number][] = [[10, 20], [15, 25]]

        const { result } = renderHook(() => useMapInstance())
        act(() => {
            result.current.fitBounds(coords)
        })

        expect(mockFitBounds).toHaveBeenCalled()
        const callArgs = mockFitBounds.mock.calls[0]
        expect(callArgs[1]).toEqual({ padding: 50, duration: 2000 })
    })

    it('fitBounds does nothing when map is null', () => {
        ;(MapInstanceContext as any)._currentValue = {
            map: null,
            ready: false,
            setMapInstance: vi.fn(),
        }

        const { result } = renderHook(() => useMapInstance())
        act(() => {
            result.current.fitBounds([[10, 20]])
        })
        expect(mockFitBounds).not.toHaveBeenCalled()
    })

    it('fitBounds does nothing with empty coordinates', () => {
        const { result } = renderHook(() => useMapInstance())
        act(() => {
            result.current.fitBounds([])
        })
        expect(mockFitBounds).not.toHaveBeenCalled()
    })

    it('ensureLayerVisible enables a disabled layer', () => {
        const { result } = renderHook(() => useMapInstance())
        act(() => {
            result.current.ensureLayerVisible('infrastructure')
        })
        expect(mockSetLayerVisibility).toHaveBeenCalledWith(
            expect.objectContaining({ infrastructure: true })
        )
    })

    it('ensureLayerVisible does nothing for already-visible layer', () => {
        const { result } = renderHook(() => useMapInstance())
        act(() => {
            result.current.ensureLayerVisible('sections')
        })
        expect(mockSetLayerVisibility).not.toHaveBeenCalled()
    })

    it('flyToWithLayer enables layer then flies', () => {
        const { result } = renderHook(() => useMapInstance())
        act(() => {
            result.current.flyToWithLayer(10, 20, 'infrastructure', 18, 1500)
        })
        expect(mockSetLayerVisibility).toHaveBeenCalledWith(
            expect.objectContaining({ infrastructure: true })
        )
        expect(mockFlyTo).toHaveBeenCalledWith({
            center: [10, 20],
            zoom: 18,
            duration: 1500,
        })
    })

    it('fitBoundsWithLayer enables layer then fits', () => {
        const coords: [number, number][] = [[10, 20], [15, 25]]
        const { result } = renderHook(() => useMapInstance())
        act(() => {
            result.current.fitBoundsWithLayer(coords, 'infrastructure', 80, 2500)
        })
        expect(mockSetLayerVisibility).toHaveBeenCalledWith(
            expect.objectContaining({ infrastructure: true })
        )
        expect(mockFitBounds).toHaveBeenCalled()
    })

})
