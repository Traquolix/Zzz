import { useContext } from 'react'
import { VehicleDataContext } from '@/context/VehicleSelectionContext'
import { useMapSelection } from './useMapSelection'

/**
 * Combined hook for vehicle data and selection.
 * Provides backward-compatible API while using unified selection.
 */
export function useVehicleSelection() {
    const dataContext = useContext(VehicleDataContext)
    if (!dataContext) {
        throw new Error('useVehicleSelection must be used within VehicleDataProvider')
    }

    const { selectedVehicle, selectVehicle } = useMapSelection()

    return {
        // Selection (from MapSelectionContext)
        selectedVehicle,
        selectVehicle,

        // Data (from VehicleDataContext)
        vehiclePositions: dataContext.vehiclePositions,
        setVehiclePositions: dataContext.setVehiclePositions
    }
}
