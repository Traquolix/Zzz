import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook } from '@testing-library/react'
import { createContext, type ReactNode } from 'react'
import type { SelectedInfrastructure } from '@/types/infrastructure'

// Mock useMapSelection
vi.mock('./useMapSelection', () => ({
    useMapSelection: vi.fn(),
}))

// Mock the context module - context created inline
vi.mock('@/context/InfrastructureContext', () => ({
    InfrastructureDataContext: createContext<any>(null),
}))

import { useMapSelection } from './useMapSelection'
import { useInfrastructure } from './useInfrastructure'
import { InfrastructureDataContext } from '@/context/InfrastructureContext'

describe('useInfrastructure', () => {
    beforeEach(() => {
        vi.clearAllMocks()
    })

    it('throws error when used outside InfrastructureDataProvider', () => {
        vi.mocked(useMapSelection).mockReturnValue({
            selectedInfrastructure: null,
            selectInfrastructure: vi.fn(),
        } as any)

        const spy = vi.spyOn(console, 'error').mockImplementation(() => {})

        expect(() => {
            renderHook(() => useInfrastructure())
        }).toThrow('useInfrastructure must be used within an InfrastructureDataProvider')

        spy.mockRestore()
    })

    it('returns infrastructure data from context', () => {
        const mockInfrastructureData = {
            infrastructures: [
                { id: 'infra-1', name: 'Substation A', fiberId: 'fiber-1', startChannel: 0, endChannel: 10, type: 'bridge' as const },
                { id: 'infra-2', name: 'Substation B', fiberId: 'fiber-2', startChannel: 10, endChannel: 20, type: 'bridge' as const },
            ],
            latestReadings: new Map([
                ['infra-1', { infrastructureId: 'infra-1', frequency: 50.5, amplitude: 10.5, timestamp: Date.now() }],
            ]),
            loading: false,
        }

        const mockMapSelection = {
            selectedInfrastructure: null,
            selectInfrastructure: vi.fn(),
        }

        vi.mocked(useMapSelection).mockReturnValue(mockMapSelection as any)

        const wrapper = ({ children }: { children: ReactNode }) => (
            <InfrastructureDataContext.Provider value={mockInfrastructureData}>
                {children}
            </InfrastructureDataContext.Provider>
        )

        const { result } = renderHook(() => useInfrastructure(), { wrapper })

        expect(result.current.infrastructures).toEqual(mockInfrastructureData.infrastructures)
        expect(result.current.latestReadings).toEqual(mockInfrastructureData.latestReadings)
        expect(result.current.loading).toBe(false)
    })

    it('returns infrastructure loading state', () => {
        const mockInfrastructureData = {
            infrastructures: [],
            latestReadings: new Map(),
            loading: true,
        }

        const mockMapSelection = {
            selectedInfrastructure: null,
            selectInfrastructure: vi.fn(),
        }

        vi.mocked(useMapSelection).mockReturnValue(mockMapSelection as any)

        const wrapper = ({ children }: { children: ReactNode }) => (
            <InfrastructureDataContext.Provider value={mockInfrastructureData}>
                {children}
            </InfrastructureDataContext.Provider>
        )

        const { result } = renderHook(() => useInfrastructure(), { wrapper })

        expect(result.current.loading).toBe(true)
    })

    it('returns selected infrastructure from map selection context', () => {
        const mockInfrastructureData = {
            infrastructures: [{ id: 'infra-1', name: 'Substation A', fiberId: 'fiber-1', startChannel: 0, endChannel: 10, type: 'bridge' as const }],
            latestReadings: new Map(),
            loading: false,
        }

        const selectedInfra: SelectedInfrastructure = {
            id: 'infra-1',
            name: 'Substation A',
            type: 'bridge',
            fiberId: 'fiber-1',
            startChannel: 0,
            endChannel: 10,
        }

        const mockMapSelection = {
            selectedInfrastructure: selectedInfra,
            selectInfrastructure: vi.fn(),
        }

        vi.mocked(useMapSelection).mockReturnValue(mockMapSelection as any)

        const wrapper = ({ children }: { children: ReactNode }) => (
            <InfrastructureDataContext.Provider value={mockInfrastructureData}>
                {children}
            </InfrastructureDataContext.Provider>
        )

        const { result } = renderHook(() => useInfrastructure(), { wrapper })

        expect(result.current.selectedInfrastructure).toEqual(selectedInfra)
    })

    it('returns selectInfrastructure function from map selection context', () => {
        const mockInfrastructureData = {
            infrastructures: [{ id: 'infra-1', name: 'Substation A', fiberId: 'fiber-1', startChannel: 0, endChannel: 10, type: 'bridge' as const }],
            latestReadings: new Map(),
            loading: false,
        }

        const mockSelectInfrastructure = vi.fn()

        const mockMapSelection = {
            selectedInfrastructure: null,
            selectInfrastructure: mockSelectInfrastructure,
        }

        vi.mocked(useMapSelection).mockReturnValue(mockMapSelection as any)

        const wrapper = ({ children }: { children: ReactNode }) => (
            <InfrastructureDataContext.Provider value={mockInfrastructureData}>
                {children}
            </InfrastructureDataContext.Provider>
        )

        const { result } = renderHook(() => useInfrastructure(), { wrapper })

        expect(result.current.selectInfrastructure).toBe(mockSelectInfrastructure)
    })

    it('combines data from both contexts', () => {
        const mockInfrastructureData = {
            infrastructures: [
                { id: 'infra-1', name: 'Substation A', fiberId: 'fiber-1', startChannel: 0, endChannel: 10, type: 'bridge' as const },
                { id: 'infra-2', name: 'Substation B', fiberId: 'fiber-2', startChannel: 10, endChannel: 20, type: 'bridge' as const },
            ],
            latestReadings: new Map([
                ['infra-1', { infrastructureId: 'infra-1', frequency: 50.5, amplitude: 10.5, timestamp: Date.now() }],
                ['infra-2', { infrastructureId: 'infra-2', frequency: 49.8, amplitude: 11.2, timestamp: Date.now() }],
            ]),
            loading: false,
        }

        const selectedInfra: SelectedInfrastructure = {
            id: 'infra-1',
            name: 'Substation A',
            type: 'bridge',
            fiberId: 'fiber-1',
            startChannel: 0,
            endChannel: 10,
        }

        const mockSelectInfrastructure = vi.fn()

        const mockMapSelection = {
            selectedInfrastructure: selectedInfra,
            selectInfrastructure: mockSelectInfrastructure,
        }

        vi.mocked(useMapSelection).mockReturnValue(mockMapSelection as any)

        const wrapper = ({ children }: { children: ReactNode }) => (
            <InfrastructureDataContext.Provider value={mockInfrastructureData}>
                {children}
            </InfrastructureDataContext.Provider>
        )

        const { result } = renderHook(() => useInfrastructure(), { wrapper })

        // Verify all data is combined correctly
        expect(result.current.infrastructures).toHaveLength(2)
        expect(result.current.latestReadings.has('infra-1')).toBe(true)
        expect(result.current.latestReadings.has('infra-2')).toBe(true)
        expect(result.current.selectedInfrastructure?.id).toBe('infra-1')
        expect(result.current.selectInfrastructure).toBe(mockSelectInfrastructure)
        expect(result.current.loading).toBe(false)
    })
})
