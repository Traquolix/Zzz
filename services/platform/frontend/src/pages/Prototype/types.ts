export type Severity = 'critical' | 'high' | 'medium' | 'low'
export type IncidentType = 'accident' | 'congestion' | 'slowdown' | 'anomaly'
export type SidebarTab = 'incidents' | 'sections' | 'settings' | 'shm' | 'channel' | 'waterfall'

export interface Fiber {
  id: string
  parentCableId: string
  direction: 0 | 1
  name: string
  color: string
  totalChannels: number
  coordinates: ([number, number] | [null, null])[]
  coordsPrecomputed?: boolean
}

export interface SpeedThresholds {
  green: number // speed >= green → green
  yellow: number // speed >= yellow → yellow
  orange: number // speed >= orange → orange
  // below orange → red
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
  speedThresholds: SpeedThresholds
}

export interface Incident {
  id: string
  fiberId: string
  type: IncidentType
  severity: Severity
  title: string
  description: string
  location: [number, number]
  timestamp: string
  resolved: boolean
  channel: number
  channelEnd?: number
  status: string
  duration?: number | null
  speedBefore?: number | null
  speedDuring?: number | null
  speedDropPercent?: number | null
}

export interface TimeSeriesPoint {
  time: string
  speed?: number
  flow?: number
  occupancy?: number
}

export interface PendingPoint {
  fiberId: string
  channel: number
  lng: number
  lat: number
}

export interface SelectedChannel {
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

export interface SectionDataPoint {
  time: string
  timestamp: number
  speed: number
  flow: number
  occupancy: number
}

export interface LiveSectionStats {
  avgSpeed: number | null
  flow: number | null
  travelTime: number | null
  occupancy: number | null
}

export type MetricKey = 'speed' | 'flow' | 'occupancy'

export interface ProtoState {
  activeTab: SidebarTab
  selectedIncidentId: string | null
  selectedSectionId: string | null
  filterSeverity: Severity | null
  hideResolved: boolean
  sectionMetric: MetricKey
  sections: Section[]
  incidents: Incident[]
  sectionCreationMode: boolean
  pendingPoint: PendingPoint | null
  showNamingDialog: boolean
  pendingSection: PendingSection | null
  sidebarOpen: boolean
  displayMode: 'dots' | 'vehicles'
  fiberThresholds: Record<string, SpeedThresholds>
  fiberColors: Record<string, string>
  selectedStructureId: string | null
  showStructuresOnMap: boolean
  showStructureLabels: boolean
  showIncidentsOnMap: boolean
  hideFibersInOverview: boolean
  show3DBuildings: boolean
  showChannelHelper: boolean
  selectedChannel: SelectedChannel | null
}

export type ProtoAction =
  | { type: 'SET_TAB'; tab: SidebarTab }
  | { type: 'SELECT_INCIDENT'; id: string }
  | { type: 'SELECT_SECTION'; id: string }
  | { type: 'CLEAR_SELECTION' }
  | { type: 'SET_FILTER_SEVERITY'; severity: Severity | null }
  | { type: 'ENTER_SECTION_CREATION' }
  | { type: 'EXIT_SECTION_CREATION' }
  | { type: 'SET_PENDING_POINT'; point: PendingPoint }
  | { type: 'OPEN_NAMING_DIALOG'; fiberId: string; startChannel: number; endChannel: number }
  | { type: 'CLOSE_NAMING_DIALOG' }
  | { type: 'CREATE_SECTION'; section: Section }
  | { type: 'DELETE_SECTION'; id: string }
  | { type: 'TOGGLE_SIDEBAR' }
  | { type: 'OPEN_SIDEBAR'; tab?: SidebarTab }
  | { type: 'SET_DISPLAY_MODE'; mode: 'dots' | 'vehicles' }
  | { type: 'SET_SECTION_METRIC'; metric: MetricKey }
  | { type: 'UPDATE_INCIDENT_DESCRIPTION'; id: string; description: string }
  | { type: 'UPDATE_SECTION_THRESHOLDS'; id: string; thresholds: SpeedThresholds }
  | { type: 'SET_FIBER_THRESHOLDS'; fiberId: string; thresholds: SpeedThresholds }
  | { type: 'SET_FIBER_COLOR'; fiberId: string; color: string }
  | { type: 'SELECT_STRUCTURE'; id: string }
  | { type: 'TOGGLE_STRUCTURES_ON_MAP' }
  | { type: 'TOGGLE_STRUCTURE_LABELS' }
  | { type: 'SELECT_CHANNEL'; channel: SelectedChannel }
  | { type: 'SET_INCIDENTS'; incidents: Incident[] }
  | { type: 'SET_SECTIONS'; sections: Section[] }
  | { type: 'TOGGLE_HIDE_RESOLVED' }
  | { type: 'TOGGLE_INCIDENTS_ON_MAP' }
  | { type: 'TOGGLE_HIDE_FIBERS_OVERVIEW' }
  | { type: 'TOGGLE_3D_BUILDINGS' }
  | { type: 'TOGGLE_CHANNEL_HELPER' }
