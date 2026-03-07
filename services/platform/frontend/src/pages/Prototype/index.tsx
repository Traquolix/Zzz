import { useReducer, useEffect, useCallback, useRef, useState, useMemo } from 'react'
import { toast } from 'sonner'
import type { ProtoState, ProtoAction, Incident, PendingPoint } from './types'
import { fibers, defaultSpeedThresholds, buildThresholdLookup, resolveDirectionalFiber, channelToCoord } from './data'
import { PrototypeMap, type PrototypeMapHandle } from './components/PrototypeMap'
import { StatusBar } from './components/StatusBar'
import { Legend } from './components/Legend'
import { SidePanel } from './components/SidePanel'
import { useDetections } from './hooks/useDetections'
import { useVehicleSim } from './hooks/useVehicleSim'
import { useLiveStats } from './hooks/useLiveStats'
import { useStructures } from './hooks/useStructures'
import { useSections } from './hooks/useSections'
import { useIncidents } from '@/hooks/useIncidents'
import { useUnseenIncidents } from './hooks/useUnseenIncidents'
import { IncidentToastStack } from './components/IncidentToastStack'
import type { Incident as ApiIncident } from '@/types/incident'
import './prototype.css'

/** Map an API incident to the prototype Incident shape. */
function toProtoIncident(api: ApiIncident): Incident {
  const fiberId = api.fiberLine
  const dirFiber = resolveDirectionalFiber(fiberId)
  const loc = channelToCoord(dirFiber, api.channel)
  const fiberName = fibers.find(f => f.id === dirFiber)?.name ?? fibers.find(f => f.id === fiberId)?.name ?? fiberId
  const typeLabel = api.type.charAt(0).toUpperCase() + api.type.slice(1)
  const title = `${typeLabel} — ${fiberName}`

  let description = `${typeLabel} detected on ${fiberName} at channel ${api.channel}.`
  if (api.speedBefore != null && api.speedDuring != null) {
    description += ` Speed dropped from ${Math.round(api.speedBefore)} to ${Math.round(api.speedDuring)} km/h.`
  }

  return {
    id: api.id,
    fiberId,
    type: api.type as Incident['type'],
    severity: api.severity as Incident['severity'],
    title,
    description,
    location: loc ?? [7.24, 43.72],
    timestamp: api.detectedAt,
    resolved: api.status !== 'active',
    channel: api.channel,
    channelEnd: api.channelEnd,
    status: api.status,
    duration: api.duration,
    speedBefore: api.speedBefore,
    speedDuring: api.speedDuring,
    speedDropPercent: api.speedDropPercent,
  }
}

const initialState: ProtoState = {
  activeTab: 'incidents',
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
  sidebarOpen: true,
  displayMode: 'dots',
  fiberThresholds: Object.fromEntries(fibers.map(f => [f.id, { ...defaultSpeedThresholds }])),
  fiberColors: Object.fromEntries(fibers.map(f => [f.id, f.color])),
  selectedStructureId: null,
  showStructuresOnMap: false,
  showStructureLabels: false,
  showIncidentsOnMap: true,
  hideFibersInOverview: false,
  show3DBuildings: false,
  showChannelHelper: false,
  selectedChannel: null,
}

function reducer(state: ProtoState, action: ProtoAction): ProtoState {
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
        pendingSection: { fiberId: action.fiberId, startChannel: action.startChannel, endChannel: action.endChannel },
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
      return { ...state, sidebarOpen: !state.sidebarOpen }
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
    default:
      return state
  }
}

export function Prototype() {
  const [state, dispatch] = useReducer(reducer, initialState)
  const [isOverview, setIsOverview] = useState(false)
  const mapRef = useRef<PrototypeMapHandle>(null)
  const { buildGeoJSON, connected, lastDetectionTsRef } = useDetections()
  const { tickAndCollect } = useVehicleSim()
  const { stats: liveStats, seriesData: liveSeriesData } = useLiveStats(state.sections)
  const structureData = useStructures(state.selectedStructureId)

  // Real incidents from API + WebSocket
  const { incidents: apiIncidents, loading: incidentsLoading } = useIncidents()
  const protoIncidents = useMemo(() => apiIncidents.map(toProtoIncident), [apiIncidents])
  const { unseenIds, hasUnseen, markSeen, toasts, dismissToast } = useUnseenIncidents(protoIncidents, incidentsLoading)

  useEffect(() => {
    dispatch({ type: 'SET_INCIDENTS', incidents: protoIncidents })
  }, [protoIncidents])

  // Real sections from API
  const { sections: apiSections, addSection, removeSection } = useSections()
  useEffect(() => {
    dispatch({ type: 'SET_SECTIONS', sections: apiSections })
  }, [apiSections])

  const thresholdLookup = useMemo(
    () => buildThresholdLookup(state.sections, state.fiberThresholds),
    [state.sections, state.fiberThresholds],
  )

  // Wrapped dispatch that intercepts DELETE_SECTION to also call the API
  const wrappedDispatch = useCallback(
    (action: ProtoAction) => {
      if (action.type === 'DELETE_SECTION') {
        removeSection(action.id).catch(() => {
          toast.error('Failed to delete section')
        })
      }
      dispatch(action)
    },
    [removeSection],
  )

  const handleIncidentClick = useCallback((id: string) => {
    dispatch({ type: 'SELECT_INCIDENT', id })
  }, [])

  const handleMapClick = useCallback(() => {
    dispatch({ type: 'CLEAR_SELECTION' })
  }, [])

  const handleFiberClick = useCallback((point: PendingPoint) => {
    dispatch({ type: 'SET_PENDING_POINT', point })
  }, [])

  const handleSectionComplete = useCallback((fiberId: string, startChannel: number, endChannel: number) => {
    dispatch({ type: 'OPEN_NAMING_DIALOG', fiberId, startChannel, endChannel })
  }, [])

  const handleStructureClick = useCallback((id: string) => {
    dispatch({ type: 'SELECT_STRUCTURE', id })
  }, [])

  const handleChannelClick = useCallback((point: PendingPoint) => {
    dispatch({ type: 'SELECT_CHANNEL', channel: point })
  }, [])

  const emptyIncidents = useMemo(() => [] as Incident[], [])
  const visibleIncidents = state.showIncidentsOnMap ? state.incidents : emptyIncidents

  // FlyTo on incident selection
  useEffect(() => {
    if (!state.selectedIncidentId) return
    const inc = state.incidents.find(i => i.id === state.selectedIncidentId)
    if (inc) {
      mapRef.current?.flyTo(inc.location, 14)
    }
  }, [state.selectedIncidentId, state.incidents])

  // FlyTo on section selection
  useEffect(() => {
    if (!state.selectedSectionId) return
    const sec = state.sections.find(s => s.id === state.selectedSectionId)
    if (!sec) return
    const fiber = fibers.find(f => f.id === sec.fiberId)
    if (!fiber) return
    const midChannel = Math.floor((sec.startChannel + sec.endChannel) / 2)
    const coord = fiber.coordinates[midChannel]
    if (coord && coord[0] != null && coord[1] != null) {
      mapRef.current?.flyTo(coord as [number, number], 13)
    }
  }, [state.selectedSectionId, state.sections])

  // FlyTo on structure selection
  useEffect(() => {
    if (!state.selectedStructureId) return
    const structure = structureData.structures.find(s => s.id === state.selectedStructureId)
    if (!structure) return
    const dirFiber = resolveDirectionalFiber(structure.fiberId)
    const midChannel = Math.floor((structure.startChannel + structure.endChannel) / 2)
    const coord = channelToCoord(dirFiber, midChannel)
    if (coord) {
      mapRef.current?.flyTo(coord, 14)
    }
  }, [state.selectedStructureId, structureData.structures])

  // Highlight selected section/incident/structure/channel on map, clear on deselect
  useEffect(() => {
    if (state.selectedSectionId) {
      mapRef.current?.highlightSection(state.selectedSectionId)
    } else if (state.selectedIncidentId) {
      mapRef.current?.highlightIncident(state.selectedIncidentId)
    } else if (state.selectedStructureId) {
      mapRef.current?.highlightStructure(state.selectedStructureId, structureData.structures)
    } else if (state.selectedChannel) {
      mapRef.current?.highlightChannel(state.selectedChannel.lng, state.selectedChannel.lat)
    } else {
      mapRef.current?.clearHighlight()
    }
  }, [
    state.selectedSectionId,
    state.selectedIncidentId,
    state.selectedStructureId,
    state.selectedChannel,
    structureData.structures,
  ])

  // Keyboard shortcuts
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return

      if (e.key === 'i') {
        dispatch({ type: 'OPEN_SIDEBAR', tab: 'incidents' })
      } else if (e.key === 's' && !state.sectionCreationMode) {
        dispatch({ type: 'OPEN_SIDEBAR', tab: 'sections' })
      } else if (e.key === 'c') {
        if (state.sectionCreationMode) {
          dispatch({ type: 'EXIT_SECTION_CREATION' })
        } else {
          dispatch({ type: 'ENTER_SECTION_CREATION' })
        }
      } else if (e.key === 'h') {
        dispatch({ type: 'OPEN_SIDEBAR', tab: 'shm' })
      } else if (e.key === 'w') {
        dispatch({ type: 'OPEN_SIDEBAR', tab: 'waterfall' })
      } else if (e.key === 'Escape') {
        if (state.showNamingDialog) {
          dispatch({ type: 'CLOSE_NAMING_DIALOG' })
        } else if (state.sectionCreationMode) {
          dispatch({ type: 'EXIT_SECTION_CREATION' })
        } else if (
          state.selectedIncidentId ||
          state.selectedSectionId ||
          state.selectedStructureId ||
          state.selectedChannel
        ) {
          dispatch({ type: 'CLEAR_SELECTION' })
        }
      }
    }

    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [
    state.sectionCreationMode,
    state.showNamingDialog,
    state.selectedIncidentId,
    state.selectedSectionId,
    state.selectedChannel,
    state.selectedStructureId,
  ])

  return (
    <div className="prototype w-screen h-screen relative overflow-hidden">
      {/* Map area — full screen */}
      <div className="absolute inset-0">
        <PrototypeMap
          ref={mapRef}
          incidents={visibleIncidents}
          onIncidentClick={handleIncidentClick}
          onMapClick={handleMapClick}
          sectionCreationMode={state.sectionCreationMode}
          pendingPoint={state.pendingPoint}
          sections={state.sections}
          selectedSectionId={state.selectedSectionId}
          onFiberClick={handleFiberClick}
          onSectionComplete={handleSectionComplete}
          buildVehicleGeoJSON={buildGeoJSON}
          tickAndCollect={tickAndCollect}
          displayMode={state.displayMode}
          liveStats={liveStats}
          onOverviewChange={setIsOverview}
          thresholdLookup={thresholdLookup}
          fiberColors={state.fiberColors}
          structures={structureData.structures}
          structureStatuses={structureData.allStatuses}
          showStructuresOnMap={state.showStructuresOnMap}
          showStructureLabels={state.showStructureLabels}
          selectedStructureId={state.selectedStructureId}
          onStructureClick={handleStructureClick}
          onChannelClick={handleChannelClick}
          sidebarOpen={state.sidebarOpen}
          hideFibersInOverview={state.hideFibersInOverview}
          show3DBuildings={state.show3DBuildings}
          showChannelHelper={state.showChannelHelper}
        />

        {/* Section creation banner */}
        {state.sectionCreationMode && (
          <div className="proto-creation-banner absolute top-4 left-1/2 -translate-x-1/2 z-30 flex items-center gap-3 px-4 py-2 rounded-lg bg-amber-500/15 border border-amber-500/30 text-sm text-amber-200">
            <span>
              {state.pendingPoint
                ? 'Click another point on the same cable to complete the section'
                : 'Click on a fiber to set the start point'}
            </span>
            <button
              onClick={() => dispatch({ type: 'EXIT_SECTION_CREATION' })}
              className="text-xs px-2 py-0.5 rounded bg-amber-500/20 hover:bg-amber-500/30 transition-colors cursor-pointer"
            >
              Cancel
            </button>
          </div>
        )}

        {/* Map overlays */}
        <StatusBar
          connected={connected}
          sectionCount={state.sections.length}
          incidentCount={state.incidents.filter(i => !i.resolved).length}
          lastDetectionTsRef={lastDetectionTsRef}
        />
      </div>

      {/* Legend — top-right, moves with sidebar */}
      <Legend
        displayMode={state.displayMode}
        onToggleDisplayMode={() =>
          dispatch({ type: 'SET_DISPLAY_MODE', mode: state.displayMode === 'dots' ? 'vehicles' : 'dots' })
        }
        isOverview={isOverview}
        sidebarOpen={state.sidebarOpen}
        hideFibersInOverview={state.hideFibersInOverview}
        onToggleHideFibers={() => dispatch({ type: 'TOGGLE_HIDE_FIBERS_OVERVIEW' })}
      />

      {/* Toast notifications for new incidents */}
      <IncidentToastStack toasts={toasts} onDismiss={dismissToast} />

      {/* Sidebar — overlays the map from the right */}
      <div className="absolute top-0 right-0 h-full z-20 pointer-events-none">
        <SidePanel
          state={state}
          dispatch={wrappedDispatch}
          liveStats={liveStats}
          liveSeriesData={liveSeriesData}
          onHighlightFiber={fiberId => mapRef.current?.highlightFiber(fiberId)}
          onHighlightSection={sectionId => mapRef.current?.highlightSection(sectionId)}
          onHighlightIncident={incidentId => mapRef.current?.highlightIncident(incidentId)}
          onClearHighlight={() => mapRef.current?.clearHighlight()}
          structureData={structureData}
          unseenIds={unseenIds}
          hasUnseen={hasUnseen}
          onMarkSeen={markSeen}
        />
      </div>

      {/* Naming dialog overlay */}
      {state.showNamingDialog && state.pendingSection && (
        <NamingDialog
          pendingSection={state.pendingSection}
          onSave={async name => {
            const ps = state.pendingSection!
            dispatch({ type: 'CLOSE_NAMING_DIALOG' })
            try {
              const section = await addSection(ps.fiberId, name, ps.startChannel, ps.endChannel)
              dispatch({ type: 'CREATE_SECTION', section })
            } catch {
              toast.error('Failed to create section')
            }
          }}
          onCancel={() => dispatch({ type: 'CLOSE_NAMING_DIALOG' })}
        />
      )}
    </div>
  )
}

function NamingDialog({
  pendingSection,
  onSave,
  onCancel,
}: {
  pendingSection: { fiberId: string; startChannel: number; endChannel: number }
  onSave: (name: string) => void
  onCancel: () => void
}) {
  const [name, setName] = useState('')
  const fiber = fibers.find(f => f.id === pendingSection.fiberId)

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-[var(--proto-surface)] border border-[var(--proto-border)] rounded-lg p-5 w-[360px] shadow-2xl">
        <h3 className="text-sm font-semibold text-[var(--proto-text)] mb-1">Name this section</h3>
        <p className="text-xs text-[var(--proto-text-muted)] mb-4">
          {fiber?.name} · Ch {pendingSection.startChannel} - {pendingSection.endChannel}
        </p>
        <input
          autoFocus
          type="text"
          value={name}
          onChange={e => setName(e.target.value)}
          onKeyDown={e => {
            if (e.key === 'Enter' && name.trim()) onSave(name.trim())
          }}
          placeholder="e.g. Zone Nord"
          className="w-full px-3 py-2 rounded-md bg-[var(--proto-base)] border border-[var(--proto-border)] text-sm text-[var(--proto-text)] placeholder:text-[var(--proto-text-muted)] outline-none focus:border-[var(--proto-accent)] mb-4"
        />
        <div className="flex justify-end gap-2">
          <button
            onClick={onCancel}
            className="px-3 py-1.5 rounded text-xs text-[var(--proto-text-secondary)] hover:text-[var(--proto-text)] transition-colors cursor-pointer"
          >
            Cancel
          </button>
          <button
            onClick={() => name.trim() && onSave(name.trim())}
            disabled={!name.trim()}
            className="px-3 py-1.5 rounded text-xs bg-[var(--proto-accent)] text-white disabled:opacity-40 cursor-pointer hover:bg-[var(--proto-accent)]/80 transition-colors"
          >
            Create
          </button>
        </div>
      </div>
    </div>
  )
}

export default Prototype
