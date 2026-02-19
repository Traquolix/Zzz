import { useState, type ReactNode } from 'react'
import type { VehiclePosition } from '@/types/selection'
import { VehicleDataContext } from './VehicleSelectionContext'

/**
 * Provider for vehicle data (positions).
 * Selection state is managed by MapSelectionProvider.
 */
export function VehicleDataProvider({ children }: { children: ReactNode }) {
    const [vehiclePositions, setVehiclePositions] = useState<VehiclePosition[]>([])

    return (
        <VehicleDataContext.Provider value={{
            vehiclePositions,
            setVehiclePositions
        }}>
            {children}
        </VehicleDataContext.Provider>
    )
}
