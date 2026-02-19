import { useState, useCallback, useMemo, type ReactNode } from 'react'
import { MapSelectionContext, type MapSelection, type MapSelectionContextType } from './MapSelectionContext'
import type { SelectedLandmark, SelectedVehicle, SelectedIncident } from '@/types/selection'
import type { SelectedSection } from '@/types/section'
import type { SelectedInfrastructure } from '@/types/infrastructure'

type Props = {
    children: ReactNode
}

export function MapSelectionProvider({ children }: Props) {
    const [selection, setSelection] = useState<MapSelection>({ type: 'none' })

    // Core select function
    const select = useCallback((newSelection: MapSelection) => {
        setSelection(newSelection)
    }, [])

    // Convenience methods
    const selectLandmark = useCallback((landmark: SelectedLandmark | null) => {
        if (landmark) {
            setSelection({ type: 'landmark', data: landmark })
        } else {
            setSelection({ type: 'none' })
        }
    }, [])

    const selectSection = useCallback((section: SelectedSection | null) => {
        if (section) {
            setSelection({ type: 'section', data: section })
        } else {
            setSelection({ type: 'none' })
        }
    }, [])

    const selectVehicle = useCallback((vehicle: SelectedVehicle | null) => {
        if (vehicle) {
            setSelection({ type: 'vehicle', data: vehicle })
        } else {
            setSelection({ type: 'none' })
        }
    }, [])

    const selectIncident = useCallback((incident: SelectedIncident | null) => {
        if (incident) {
            setSelection({ type: 'incident', data: incident })
        } else {
            setSelection({ type: 'none' })
        }
    }, [])

    const selectInfrastructure = useCallback((infrastructure: SelectedInfrastructure | null) => {
        if (infrastructure) {
            setSelection({ type: 'infrastructure', data: infrastructure })
        } else {
            setSelection({ type: 'none' })
        }
    }, [])

    // Convenience getters
    const selectedLandmark = selection.type === 'landmark' ? selection.data : null
    const selectedSection = selection.type === 'section' ? selection.data : null
    const selectedVehicle = selection.type === 'vehicle' ? selection.data : null
    const selectedIncident = selection.type === 'incident' ? selection.data : null
    const selectedInfrastructure = selection.type === 'infrastructure' ? selection.data : null

    const value: MapSelectionContextType = useMemo(() => ({
        selection,
        select,
        selectLandmark,
        selectSection,
        selectVehicle,
        selectIncident,
        selectInfrastructure,
        selectedLandmark,
        selectedSection,
        selectedVehicle,
        selectedIncident,
        selectedInfrastructure
    }), [selection, select, selectLandmark, selectSection, selectVehicle, selectIncident, selectInfrastructure])

    return (
        <MapSelectionContext.Provider value={value}>
            {children}
        </MapSelectionContext.Provider>
    )
}
