import { createContext } from 'react'
import type { SelectedLandmark, SelectedVehicle, SelectedIncident } from '@/types/selection'
import type { SelectedSection } from '@/types/section'
import type { SelectedInfrastructure } from '@/types/infrastructure'

/**
 * Discriminated union for map selection state.
 * Only one item can be selected at a time.
 */
export type MapSelection =
    | { type: 'none' }
    | { type: 'landmark'; data: SelectedLandmark }
    | { type: 'section'; data: SelectedSection }
    | { type: 'vehicle'; data: SelectedVehicle }
    | { type: 'incident'; data: SelectedIncident }
    | { type: 'infrastructure'; data: SelectedInfrastructure }

export type MapSelectionContextType = {
    // Current selection (discriminated union)
    selection: MapSelection

    // Single select function - automatically deselects others
    select: (selection: MapSelection) => void

    // Convenience methods (internally call select)
    selectLandmark: (landmark: SelectedLandmark | null) => void
    selectSection: (section: SelectedSection | null) => void
    selectVehicle: (vehicle: SelectedVehicle | null) => void
    selectIncident: (incident: SelectedIncident | null) => void
    selectInfrastructure: (infrastructure: SelectedInfrastructure | null) => void

    // Convenience getters
    selectedLandmark: SelectedLandmark | null
    selectedSection: SelectedSection | null
    selectedVehicle: SelectedVehicle | null
    selectedIncident: SelectedIncident | null
    selectedInfrastructure: SelectedInfrastructure | null
}

export const MapSelectionContext = createContext<MapSelectionContextType | null>(null)
