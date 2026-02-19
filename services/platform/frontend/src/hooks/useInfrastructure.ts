import { useContext } from 'react'
import { InfrastructureDataContext } from '@/context/InfrastructureContext'
import { useMapSelection } from './useMapSelection'

/**
 * Hook to access infrastructure data and selection.
 * Combines data from InfrastructureDataContext with selection from MapSelectionContext.
 */
export function useInfrastructure() {
    const dataContext = useContext(InfrastructureDataContext)
    if (!dataContext) {
        throw new Error('useInfrastructure must be used within an InfrastructureDataProvider')
    }

    const { selectedInfrastructure, selectInfrastructure } = useMapSelection()

    return {
        // Data from InfrastructureDataContext
        infrastructures: dataContext.infrastructures,
        latestReadings: dataContext.latestReadings,
        loading: dataContext.loading,

        // Selection from MapSelectionContext
        selectedInfrastructure,
        selectInfrastructure
    }
}
