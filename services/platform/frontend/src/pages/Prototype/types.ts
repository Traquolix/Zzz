export type Severity = 'critical' | 'high' | 'medium' | 'low'
export type IncidentType = 'accident' | 'construction' | 'weather' | 'anomaly' | 'intrusion'

export interface Fiber {
    id: string
    parentCableId: string
    direction: 0 | 1
    name: string
    color: string
    totalChannels: number
    coordinates: [number, number][]
}

export interface Section {
    id: string
    fiberId: string
    name: string
    startChannel: number
    endChannel: number
    avgSpeed: number
    flow: number
    occupancy: number
    travelTime: number
    speedHistory: number[]
    countHistory: number[]
}

export interface Incident {
    id: string
    fiberId: string
    sectionId: string
    type: IncidentType
    severity: Severity
    title: string
    description: string
    location: [number, number]
    timestamp: string
    resolved: boolean
}

export interface Vehicle {
    id: string
    fiberId: string
    position: [number, number]
    speed: number
    direction: 0 | 1
}

export interface TimeSeriesPoint {
    time: string
    speed: number
    flow: number
    occupancy: number
}

export interface PendingPoint {
    fiberId: string
    channel: number
    lng: number
    lat: number
}

export interface PendingSection {
    fiberId: string
    startChannel: number
    endChannel: number
}

export interface ProtoState {
    layer: 0 | 1 | 2
    incidentPanelOpen: boolean
    sectionPanelOpen: boolean
    selectedIncidentId: string | null
    selectedSectionId: string | null
    filterSeverity: Severity | null
    sections: Section[]
    sectionCreationMode: boolean
    pendingPoint: PendingPoint | null
    showNamingDialog: boolean
    pendingSection: PendingSection | null
}

export type ProtoAction =
    | { type: 'OPEN_INCIDENTS' }
    | { type: 'OPEN_SECTIONS' }
    | { type: 'CLOSE_PANELS' }
    | { type: 'SELECT_INCIDENT'; id: string }
    | { type: 'SELECT_INCIDENT_FROM_MAP'; id: string }
    | { type: 'SELECT_SECTION'; id: string }
    | { type: 'BACK' }
    | { type: 'SET_FILTER_SEVERITY'; severity: Severity | null }
    | { type: 'ENTER_SECTION_CREATION' }
    | { type: 'EXIT_SECTION_CREATION' }
    | { type: 'SET_PENDING_POINT'; point: PendingPoint }
    | { type: 'OPEN_NAMING_DIALOG'; fiberId: string; startChannel: number; endChannel: number }
    | { type: 'CLOSE_NAMING_DIALOG' }
    | { type: 'CREATE_SECTION'; section: Section }
    | { type: 'DELETE_SECTION'; id: string }
