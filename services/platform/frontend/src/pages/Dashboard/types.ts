import type { IncidentType, DisplayIncident } from '@/types/incident'

export type { IncidentType, DisplayIncident }
export type SidebarTab = 'incidents' | 'sections' | 'settings' | 'shm' | 'channel' | 'waterfall' | 'dataHub'

/**
 * A directional fiber — one direction on a physical cable.
 *
 * **Cable** = a physical fiber optic cable installation (e.g. "carros").
 * Each cable produces two **Fibers**, one per direction (0 and 1).
 *
 * The API and domain types use the cable ID (`fiberId`) + `direction` as
 * separate fields. Internally, each Fiber has a composite `id` ("carros:0")
 * used only for keying caches and maps inside `data.ts`.
 */
export interface Fiber {
  id: string // internal composite key ("carros:0"), not used in domain types
  parentCableId: string // the physical cable ID ("carros"), matches API fiberId
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
  fiberId: string // raw cable ID (e.g. "carros"), not the internal composite ID
  direction: 0 | 1
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

export interface TimeSeriesPoint {
  time: string
  speed?: number
  flow?: number
  occupancy?: number
}

export interface PendingPoint {
  fiberId: string // raw cable ID (e.g. "carros"), not the internal composite ID
  direction: 0 | 1
  channel: number
  lng: number
  lat: number
}

export interface SelectedChannel {
  fiberId: string // raw cable ID (e.g. "carros"), not the internal composite ID
  direction: 0 | 1
  channel: number
  lng: number
  lat: number
}

export interface PendingSection {
  fiberId: string // raw cable ID (e.g. "carros"), not the internal composite ID
  direction: 0 | 1
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

export interface MapPageState {
  activeTab: SidebarTab
  selectedIncidentId: string | null
  selectedSectionId: string | null
  filterTags: string[]
  hideResolved: boolean
  sectionMetric: MetricKey
  sections: Section[]
  incidents: DisplayIncident[]
  sectionCreationMode: boolean
  pendingPoint: PendingPoint | null
  showNamingDialog: boolean
  pendingSection: PendingSection | null
  sidebarOpen: boolean
  sidebarExpanded: boolean
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
  showFullCable: boolean
  selectedChannel: SelectedChannel | null
}

export type MapPageAction =
  | { type: 'SET_TAB'; tab: SidebarTab }
  | { type: 'SELECT_INCIDENT'; id: string }
  | { type: 'SELECT_SECTION'; id: string }
  | { type: 'CLEAR_SELECTION' }
  | { type: 'SET_FILTER_TAGS'; tags: string[] }
  | { type: 'ENTER_SECTION_CREATION' }
  | { type: 'EXIT_SECTION_CREATION' }
  | { type: 'SET_PENDING_POINT'; point: PendingPoint }
  | { type: 'OPEN_NAMING_DIALOG'; fiberId: string; direction: 0 | 1; startChannel: number; endChannel: number }
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
  | { type: 'SET_INCIDENTS'; incidents: DisplayIncident[] }
  | { type: 'SET_SECTIONS'; sections: Section[] }
  | { type: 'TOGGLE_HIDE_RESOLVED' }
  | { type: 'TOGGLE_INCIDENTS_ON_MAP' }
  | { type: 'TOGGLE_HIDE_FIBERS_OVERVIEW' }
  | { type: 'TOGGLE_3D_BUILDINGS' }
  | { type: 'TOGGLE_CHANNEL_HELPER' }
  | { type: 'TOGGLE_SHOW_FULL_CABLE' }
  | { type: 'TOGGLE_SIDEBAR_EXPANDED' }
  | { type: 'RESET_SIDEBAR_EXPANDED' }
  | { type: 'OPEN_PANEL'; tab: SidebarTab }
  | { type: 'INIT_FIBER_DEFAULTS'; fibers: Fiber[] }
