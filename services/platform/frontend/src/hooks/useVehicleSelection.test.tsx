import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook } from '@testing-library/react'
import { createContext, type ReactNode } from 'react'
import type { SelectedVehicle, VehiclePosition } from '@/types/selection'

// Mock useMapSelection
vi.mock('./useMapSelection', () => ({
    useMapSelection: vi.fn(),
}))

// Mock VehicleDataContext
vi.mock('@/context/VehicleSelectionContext', () => ({
    VehicleDataContext: createContext<any>(null),
}))

import { useMapSelection } from './useMapSelection'
import { useVehicleSelection } from './useVehicleSelection'
import { VehicleDataContext } from '@/context/VehicleSelectionContext'

describe('useVehicleSelection', () => {
    beforeEach(() => {
        vi.clearAllMocks()
    })

    it('throws error when used outside VehicleDataProvider', () => {
        vi.mocked(useMapSelection).mockReturnValue({
            selectedVehicle: null,
            selectVehicle: vi.fn(),
        } as any)

        const spy = vi.spyOn(console, 'error').mockImplementation(() => {})

        expect(() => {
            renderHook(() => useVehicleSelection())
        }).toThrow('useVehicleSelection must be used within VehicleDataProvider')

        spy.mockRestore()
    })

    it('returns vehicle positions from context', () => {
        const mockVehiclePositions: VehiclePosition[] = [
            {
                id: 'vehicle-1',
                fiberId: 'fiber-1',
                position: [100, 200, 50],
                angle: 45,
                speed: 60,
                detectionSpeed: 60,
                channel: 5,
                direction: 0,
                isDetectionMarker: false,
            },
            {
                id: 'vehicle-2',
                fiberId: 'fiber-2',
                position: [150, 250, 50],
                angle: 90,
                speed: 70,
                detectionSpeed: 70,
                channel: 10,
                direction: 1,
                isDetectionMarker: false,
            },
        ]

        const mockDataContext = {
            vehiclePositions: mockVehiclePositions,
            setVehiclePositions: vi.fn(),
        }

        const mockMapSelection = {
            selectedVehicle: null,
            selectVehicle: vi.fn(),
        }

        vi.mocked(useMapSelection).mockReturnValue(mockMapSelection as any)

        const wrapper = ({ children }: { children: ReactNode }) => (
            <VehicleDataContext.Provider value={mockDataContext}>
                {children}
            </VehicleDataContext.Provider>
        )

        const { result } = renderHook(() => useVehicleSelection(), { wrapper })

        expect(result.current.vehiclePositions).toEqual(mockVehiclePositions)
        expect(result.current.vehiclePositions).toHaveLength(2)
    })

    it('returns selected vehicle from map selection context', () => {
        const selectedVehicle: SelectedVehicle = {
            id: 'vehicle-1',
            speed: 60,
            detectionSpeed: 60,
            channel: 5,
            direction: 0,
            screenX: 100,
            screenY: 200,
        }

        const mockDataContext = {
            vehiclePositions: [],
            setVehiclePositions: vi.fn(),
        }

        const mockMapSelection = {
            selectedVehicle,
            selectVehicle: vi.fn(),
        }

        vi.mocked(useMapSelection).mockReturnValue(mockMapSelection as any)

        const wrapper = ({ children }: { children: ReactNode }) => (
            <VehicleDataContext.Provider value={mockDataContext}>
                {children}
            </VehicleDataContext.Provider>
        )

        const { result } = renderHook(() => useVehicleSelection(), { wrapper })

        expect(result.current.selectedVehicle).toEqual(selectedVehicle)
        expect(result.current.selectedVehicle?.id).toBe('vehicle-1')
    })

    it('returns selectVehicle function from map selection context', () => {
        const mockSelectVehicle = vi.fn()

        const mockDataContext = {
            vehiclePositions: [],
            setVehiclePositions: vi.fn(),
        }

        const mockMapSelection = {
            selectedVehicle: null,
            selectVehicle: mockSelectVehicle,
        }

        vi.mocked(useMapSelection).mockReturnValue(mockMapSelection as any)

        const wrapper = ({ children }: { children: ReactNode }) => (
            <VehicleDataContext.Provider value={mockDataContext}>
                {children}
            </VehicleDataContext.Provider>
        )

        const { result } = renderHook(() => useVehicleSelection(), { wrapper })

        expect(result.current.selectVehicle).toBe(mockSelectVehicle)
    })

    it('returns setVehiclePositions function from data context', () => {
        const mockSetVehiclePositions = vi.fn()

        const mockDataContext = {
            vehiclePositions: [],
            setVehiclePositions: mockSetVehiclePositions,
        }

        const mockMapSelection = {
            selectedVehicle: null,
            selectVehicle: vi.fn(),
        }

        vi.mocked(useMapSelection).mockReturnValue(mockMapSelection as any)

        const wrapper = ({ children }: { children: ReactNode }) => (
            <VehicleDataContext.Provider value={mockDataContext}>
                {children}
            </VehicleDataContext.Provider>
        )

        const { result } = renderHook(() => useVehicleSelection(), { wrapper })

        expect(result.current.setVehiclePositions).toBe(mockSetVehiclePositions)
    })

    it('combines selection and position data correctly', () => {
        const mockVehiclePositions: VehiclePosition[] = [
            {
                id: 'vehicle-1',
                fiberId: 'fiber-1',
                position: [100, 200, 50],
                angle: 45,
                speed: 60,
                detectionSpeed: 60,
                channel: 5,
                direction: 0,
                isDetectionMarker: false,
            },
        ]

        const selectedVehicle: SelectedVehicle = {
            id: 'vehicle-1',
            speed: 60,
            detectionSpeed: 60,
            channel: 5,
            direction: 0,
            screenX: 100,
            screenY: 200,
        }

        const mockSelectVehicle = vi.fn()
        const mockSetVehiclePositions = vi.fn()

        const mockDataContext = {
            vehiclePositions: mockVehiclePositions,
            setVehiclePositions: mockSetVehiclePositions,
        }

        const mockMapSelection = {
            selectedVehicle,
            selectVehicle: mockSelectVehicle,
        }

        vi.mocked(useMapSelection).mockReturnValue(mockMapSelection as any)

        const wrapper = ({ children }: { children: ReactNode }) => (
            <VehicleDataContext.Provider value={mockDataContext}>
                {children}
            </VehicleDataContext.Provider>
        )

        const { result } = renderHook(() => useVehicleSelection(), { wrapper })

        expect(result.current.vehiclePositions).toEqual(mockVehiclePositions)
        expect(result.current.selectedVehicle).toEqual(selectedVehicle)
        expect(result.current.selectVehicle).toBe(mockSelectVehicle)
        expect(result.current.setVehiclePositions).toBe(mockSetVehiclePositions)
    })

    it('handles empty vehicle positions array', () => {
        const mockDataContext = {
            vehiclePositions: [],
            setVehiclePositions: vi.fn(),
        }

        const mockMapSelection = {
            selectedVehicle: null,
            selectVehicle: vi.fn(),
        }

        vi.mocked(useMapSelection).mockReturnValue(mockMapSelection as any)

        const wrapper = ({ children }: { children: ReactNode }) => (
            <VehicleDataContext.Provider value={mockDataContext}>
                {children}
            </VehicleDataContext.Provider>
        )

        const { result } = renderHook(() => useVehicleSelection(), { wrapper })

        expect(result.current.vehiclePositions).toEqual([])
        expect(result.current.vehiclePositions).toHaveLength(0)
    })

    it('handles null selected vehicle', () => {
        const mockVehiclePositions: VehiclePosition[] = [
            {
                id: 'vehicle-1',
                fiberId: 'fiber-1',
                position: [100, 200, 50],
                angle: 45,
                speed: 60,
                detectionSpeed: 60,
                channel: 5,
                direction: 0,
                isDetectionMarker: false,
            },
        ]

        const mockDataContext = {
            vehiclePositions: mockVehiclePositions,
            setVehiclePositions: vi.fn(),
        }

        const mockMapSelection = {
            selectedVehicle: null,
            selectVehicle: vi.fn(),
        }

        vi.mocked(useMapSelection).mockReturnValue(mockMapSelection as any)

        const wrapper = ({ children }: { children: ReactNode }) => (
            <VehicleDataContext.Provider value={mockDataContext}>
                {children}
            </VehicleDataContext.Provider>
        )

        const { result } = renderHook(() => useVehicleSelection(), { wrapper })

        expect(result.current.selectedVehicle).toBeNull()
        expect(result.current.vehiclePositions).toHaveLength(1)
    })
})
