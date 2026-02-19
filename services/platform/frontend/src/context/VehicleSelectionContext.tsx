import { createContext } from 'react'
import type { VehiclePosition } from '@/types/selection'

/**
 * Context for vehicle data (positions).
 * Selection state is managed by MapSelectionContext.
 */
export type VehicleDataContextType = {
    vehiclePositions: VehiclePosition[]
    setVehiclePositions: (positions: VehiclePosition[]) => void
}

export const VehicleDataContext = createContext<VehicleDataContextType | null>(null)
