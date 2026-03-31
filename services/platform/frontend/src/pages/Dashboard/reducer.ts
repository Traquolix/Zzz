import type { MapPageState, MapPageAction } from './types'
import { defaultSpeedThresholds } from './data'

export const initialState: MapPageState = {
  activeTab: 'sections',
  selectedIncidentId: null,
  selectedSectionId: null,
  filterSeverity: null,
  hideResolved: true,
  sectionMetric: 'speed',
  sections: [],
  incidents: [],
  sectionCreationMode: false,
  pendingPoint: null,
  showNamingDialog: false,
  pendingSection: null,
  sidebarOpen: false,
  sidebarExpanded: false,
  displayMode: 'dots',
  fiberThresholds: {},
  fiberColors: {},
  selectedStructureId: null,
  showStructuresOnMap: false,
  showStructureLabels: false,
  showIncidentsOnMap: true,
  hideFibersInOverview: false,
  show3DBuildings: false,
  showChannelHelper: false,
  showFullCable: false,
  selectedChannel: null,
}

export function reducer(state: MapPageState, action: MapPageAction): MapPageState {
  switch (action.type) {
    case 'SET_TAB':
      return {
        ...state,
        activeTab: action.tab,
        selectedIncidentId: null,
        selectedSectionId: null,
        selectedStructureId: null,
        selectedChannel: null,
        filterSeverity: null,
      }
    case 'SELECT_INCIDENT':
      return {
        ...state,
        activeTab: 'incidents',
        selectedIncidentId: action.id,
        selectedSectionId: null,
        selectedStructureId: null,
        selectedChannel: null,
        sectionCreationMode: false,
        pendingPoint: null,
        sidebarOpen: true,
      }
    case 'SELECT_SECTION':
      return {
        ...state,
        activeTab: 'sections',
        selectedSectionId: action.id,
        selectedIncidentId: null,
        selectedStructureId: null,
        selectedChannel: null,
      }
    case 'CLEAR_SELECTION':
      return {
        ...state,
        selectedIncidentId: null,
        selectedSectionId: null,
        selectedStructureId: null,
        selectedChannel: null,
      }
    case 'SET_FILTER_SEVERITY':
      return { ...state, filterSeverity: action.severity }
    case 'ENTER_SECTION_CREATION':
      return {
        ...state,
        sectionCreationMode: true,
        pendingPoint: null,
        selectedIncidentId: null,
        selectedSectionId: null,
      }
    case 'EXIT_SECTION_CREATION':
      return {
        ...state,
        sectionCreationMode: false,
        pendingPoint: null,
        showNamingDialog: false,
        pendingSection: null,
      }
    case 'SET_PENDING_POINT':
      return { ...state, pendingPoint: action.point }
    case 'OPEN_NAMING_DIALOG':
      return {
        ...state,
        showNamingDialog: true,
        pendingSection: {
          fiberId: action.fiberId,
          direction: action.direction,
          startChannel: action.startChannel,
          endChannel: action.endChannel,
        },
        sectionCreationMode: false,
        pendingPoint: null,
      }
    case 'CLOSE_NAMING_DIALOG':
      return {
        ...state,
        showNamingDialog: false,
        pendingSection: null,
      }
    case 'CREATE_SECTION':
      return {
        ...state,
        sections: [...state.sections, action.section],
        showNamingDialog: false,
        pendingSection: null,
        sectionCreationMode: false,
        pendingPoint: null,
      }
    case 'DELETE_SECTION':
      return {
        ...state,
        sections: state.sections.filter(s => s.id !== action.id),
        selectedSectionId: state.selectedSectionId === action.id ? null : state.selectedSectionId,
      }
    case 'TOGGLE_SIDEBAR':
      if (state.sidebarOpen) {
        return {
          ...state,
          sidebarOpen: false,
          selectedSectionId: null,
          selectedIncidentId: null,
          selectedStructureId: null,
          selectedChannel: null,
        }
      }
      return { ...state, sidebarOpen: true }
    case 'RESET_SIDEBAR_EXPANDED':
      return { ...state, sidebarExpanded: false }
    case 'OPEN_SIDEBAR':
      return {
        ...state,
        sidebarOpen: true,
        ...(action.tab
          ? {
              activeTab: action.tab,
              selectedIncidentId: null,
              selectedSectionId: null,
            }
          : {}),
      }
    case 'SET_DISPLAY_MODE':
      return { ...state, displayMode: action.mode, selectedSectionId: null, selectedIncidentId: null }
    case 'SET_SECTION_METRIC':
      return { ...state, sectionMetric: action.metric }
    case 'UPDATE_INCIDENT_DESCRIPTION':
      return {
        ...state,
        incidents: state.incidents.map(inc =>
          inc.id === action.id ? { ...inc, description: action.description } : inc,
        ),
      }
    case 'UPDATE_SECTION_THRESHOLDS':
      return {
        ...state,
        sections: state.sections.map(s => (s.id === action.id ? { ...s, speedThresholds: action.thresholds } : s)),
      }
    case 'SET_FIBER_THRESHOLDS':
      return {
        ...state,
        fiberThresholds: { ...state.fiberThresholds, [action.fiberId]: action.thresholds },
      }
    case 'SET_FIBER_COLOR':
      return {
        ...state,
        fiberColors: { ...state.fiberColors, [action.fiberId]: action.color },
      }
    case 'SELECT_STRUCTURE':
      return {
        ...state,
        activeTab: 'shm',
        selectedStructureId: action.id,
        selectedIncidentId: null,
        selectedSectionId: null,
        selectedChannel: null,
        sectionCreationMode: false,
        pendingPoint: null,
      }
    case 'TOGGLE_STRUCTURES_ON_MAP':
      return { ...state, showStructuresOnMap: !state.showStructuresOnMap }
    case 'TOGGLE_STRUCTURE_LABELS':
      return { ...state, showStructureLabels: !state.showStructureLabels }
    case 'SELECT_CHANNEL':
      return {
        ...state,
        activeTab: 'channel',
        selectedChannel: action.channel,
        selectedIncidentId: null,
        selectedSectionId: null,
        selectedStructureId: null,
        sectionCreationMode: false,
        pendingPoint: null,
        sidebarOpen: true,
      }
    case 'SET_INCIDENTS':
      return { ...state, incidents: action.incidents }
    case 'SET_SECTIONS':
      return { ...state, sections: action.sections }
    case 'TOGGLE_HIDE_RESOLVED':
      return { ...state, hideResolved: !state.hideResolved }
    case 'TOGGLE_INCIDENTS_ON_MAP':
      return { ...state, showIncidentsOnMap: !state.showIncidentsOnMap }
    case 'TOGGLE_HIDE_FIBERS_OVERVIEW':
      return { ...state, hideFibersInOverview: !state.hideFibersInOverview }
    case 'TOGGLE_3D_BUILDINGS':
      return { ...state, show3DBuildings: !state.show3DBuildings }
    case 'TOGGLE_CHANNEL_HELPER':
      return { ...state, showChannelHelper: !state.showChannelHelper }
    case 'TOGGLE_SHOW_FULL_CABLE':
      return { ...state, showFullCable: !state.showFullCable }
    case 'TOGGLE_SIDEBAR_EXPANDED':
      return { ...state, sidebarExpanded: !state.sidebarExpanded }
    case 'OPEN_PANEL':
      return {
        ...state,
        activeTab: action.tab,
        sidebarOpen: true,
        selectedIncidentId: null,
        selectedSectionId: null,
        selectedStructureId: null,
        selectedChannel: null,
      }
    case 'INIT_FIBER_DEFAULTS': {
      if (Object.keys(state.fiberThresholds).length > 0) return state
      return {
        ...state,
        fiberThresholds: Object.fromEntries(action.fibers.map(f => [f.id, { ...defaultSpeedThresholds }])),
        fiberColors: Object.fromEntries(action.fibers.map(f => [f.id, f.color])),
      }
    }
    default:
      return state
  }
}
