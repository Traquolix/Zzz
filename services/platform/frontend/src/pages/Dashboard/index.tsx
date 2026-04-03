import { useEffect, useCallback, useRef, useState, useMemo } from 'react'
import { toast } from 'sonner'
import type { Fiber, DisplayIncident, PendingPoint } from './types'
import { buildThresholdLookup } from './data'
import { FiberProvider, useFiberData } from './context/FiberContext'
import { DashboardProvider, useDashboard } from './context/DashboardContext'
import { DashboardMap, type DashboardMapHandle } from './components/DashboardMap'
import { StatusBar } from './components/StatusBar'
import { Legend } from './components/Legend'
import { SidePanel } from './components/SidePanel'
import { useDetections } from './hooks/useDetections'
import { useVehicleSim } from './hooks/useVehicleSim'
import { useLiveStats } from './hooks/useLiveStats'
import { useInfrastructure } from './hooks/useInfrastructure'
import { useSections } from './hooks/useSections'
import { useConfigUpdates } from '@/hooks/useConfigUpdates'
import { useIncidents } from '@/hooks/useIncidents'
import { useUnseenIncidents } from './hooks/useUnseenIncidents'
import { useDisplayIncident } from './hooks/useDisplayIncident'
import { IncidentToastStack } from './components/IncidentToastStack'
import { UserMenu } from './components/UserMenu'
import { ConnectionBanner } from './components/ConnectionBanner'
import { SidebarRefContext } from './hooks/useSidebarWidth'
import './dashboard.css'

/** Wrapper that places providers above the inner Dashboard. */
export function Dashboard() {
  const { removeSection } = useSections()
  return (
    <FiberProvider>
      <DashboardProvider removeSection={removeSection}>
        <DashboardInner />
      </DashboardProvider>
    </FiberProvider>
  )
}

function DashboardInner() {
  const { state, dispatch } = useDashboard()
  const [isOverview, setIsOverview] = useState(false)
  const mapRef = useRef<DashboardMapHandle>(null)
  const sidebarRef = useRef<HTMLDivElement>(null)
  useConfigUpdates()

  // Fiber context
  const { findFiber, channelToCoord, fibers: fiberList } = useFiberData()

  // Initialize fiber defaults when fibers load
  useEffect(() => {
    if (fiberList.length > 0) {
      dispatch({ type: 'INIT_FIBER_DEFAULTS', fibers: fiberList })
    }
  }, [fiberList, dispatch])

  const toDisplayIncident = useDisplayIncident()

  const { buildGeoJSON, connected, lastDetectionTsRef } = useDetections(findFiber, channelToCoord)
  const { tickAndCollect } = useVehicleSim(fiberList)
  const { stats: liveStats, seriesData: liveSeriesData } = useLiveStats(state.sections)
  const infrastructure = useInfrastructure()

  // Real incidents from API + WebSocket
  const { incidents: apiIncidents, loading: incidentsLoading } = useIncidents()
  const displayIncidents = useMemo(() => apiIncidents.map(toDisplayIncident), [apiIncidents, toDisplayIncident])
  const { unseenIds, hasUnseen, markSeen, markAllSeen, toasts, dismissToast } = useUnseenIncidents(
    displayIncidents,
    incidentsLoading,
  )

  useEffect(() => {
    dispatch({ type: 'SET_INCIDENTS', incidents: displayIncidents })
  }, [displayIncidents, dispatch])

  // Real sections from API
  const { sections: apiSections, addSection } = useSections()
  useEffect(() => {
    dispatch({ type: 'SET_SECTIONS', sections: apiSections })
  }, [apiSections, dispatch])

  const thresholdLookup = useMemo(
    () => buildThresholdLookup(state.sections, state.fiberThresholds, findFiber),
    [state.sections, state.fiberThresholds, findFiber],
  )

  const handleIncidentClick = useCallback(
    (id: string) => {
      dispatch({ type: 'SELECT_INCIDENT', id })
    },
    [dispatch],
  )

  const handleMapClick = useCallback(() => {
    dispatch({ type: 'CLEAR_SELECTION' })
  }, [dispatch])

  const handleFiberClick = useCallback(
    (point: PendingPoint) => {
      dispatch({ type: 'SET_PENDING_POINT', point })
    },
    [dispatch],
  )

  const handleSectionComplete = useCallback(
    (fiberId: string, direction: 0 | 1, startChannel: number, endChannel: number) => {
      dispatch({ type: 'OPEN_NAMING_DIALOG', fiberId, direction, startChannel, endChannel })
    },
    [dispatch],
  )

  const handleStructureClick = useCallback(
    (id: string) => {
      dispatch({ type: 'SELECT_STRUCTURE', id })
    },
    [dispatch],
  )

  const handleChannelClick = useCallback(
    (point: PendingPoint) => {
      dispatch({ type: 'SELECT_CHANNEL', channel: point })
    },
    [dispatch],
  )

  const emptyIncidents = useMemo(() => [] as DisplayIncident[], [])
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
    const secFiber = findFiber(sec.fiberId, sec.direction)
    if (!secFiber) return
    const midChannel = Math.floor((sec.startChannel + sec.endChannel) / 2)
    const coord = channelToCoord(secFiber, midChannel)
    if (coord) {
      mapRef.current?.flyTo(coord, 13)
    }
  }, [state.selectedSectionId, state.sections, findFiber, channelToCoord])

  // FlyTo on structure selection
  useEffect(() => {
    if (!state.selectedStructureId) return
    const structure = infrastructure.structures.find(s => s.id === state.selectedStructureId)
    if (!structure) return
    const sFiber = findFiber(structure.fiberId, structure.direction ?? 0)
    const midChannel = Math.floor((structure.startChannel + structure.endChannel) / 2)
    const coord = sFiber ? channelToCoord(sFiber, midChannel) : null
    if (coord) {
      mapRef.current?.flyTo(coord, 14)
    }
  }, [state.selectedStructureId, infrastructure.structures, findFiber, channelToCoord])

  // Highlight selected section/incident/structure/channel on map, clear on deselect
  useEffect(() => {
    if (state.selectedSectionId) {
      mapRef.current?.highlightSection(state.selectedSectionId)
    } else if (state.selectedIncidentId) {
      mapRef.current?.highlightIncident(state.selectedIncidentId)
    } else if (state.selectedStructureId) {
      mapRef.current?.highlightStructure(state.selectedStructureId, infrastructure.structures)
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
    infrastructure.structures,
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
    dispatch,
    state.sectionCreationMode,
    state.showNamingDialog,
    state.selectedIncidentId,
    state.selectedSectionId,
    state.selectedChannel,
    state.selectedStructureId,
  ])

  return (
    <SidebarRefContext.Provider value={sidebarRef}>
      <div className="dashboard w-screen h-screen relative overflow-hidden">
        {/* Map area -- full screen */}
        <div className="absolute inset-0">
          <DashboardMap
            ref={mapRef}
            incidents={visibleIncidents}
            onIncidentClick={handleIncidentClick}
            onMapClick={handleMapClick}
            sectionCreationMode={state.sectionCreationMode}
            pendingPoint={state.pendingPoint}
            sections={state.sections}
            onFiberClick={handleFiberClick}
            onSectionComplete={handleSectionComplete}
            buildVehicleGeoJSON={buildGeoJSON}
            tickAndCollect={tickAndCollect}
            displayMode={state.displayMode}
            liveStats={liveStats}
            onOverviewChange={setIsOverview}
            thresholdLookup={thresholdLookup}
            fiberColors={state.fiberColors}
            structures={infrastructure.structures}
            structureStatuses={infrastructure.allStatuses}
            showStructuresOnMap={state.showStructuresOnMap}
            showStructureLabels={state.showStructureLabels}
            selectedStructureId={state.selectedStructureId}
            onStructureClick={handleStructureClick}
            onChannelClick={handleChannelClick}
            sidebarOpen={state.sidebarOpen}
            hideFibersInOverview={state.hideFibersInOverview}
            show3DBuildings={state.show3DBuildings}
            showChannelHelper={state.showChannelHelper}
            showFullCable={state.showFullCable}
          />

          {/* Section creation banner */}
          {state.sectionCreationMode && (
            <div className="dash-creation-banner absolute top-4 left-1/2 -translate-x-1/2 z-30 flex items-center gap-3 px-4 py-2 rounded-lg bg-amber-500/15 border border-amber-500/30 text-sm text-amber-200">
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

          <ConnectionBanner />

          {/* Map overlays -- user button + status bar */}
          <div className="absolute top-4 left-4 z-10 flex items-center gap-2.5">
            <UserMenu />
            <StatusBar
              connected={connected}
              sectionCount={state.sections.length}
              incidentCount={state.incidents.filter(i => !i.resolved).length}
              lastDetectionTsRef={lastDetectionTsRef}
            />
          </div>
        </div>

        {/* Legend -- top-right, moves with sidebar */}
        <Legend
          displayMode={state.displayMode}
          onToggleDisplayMode={() =>
            dispatch({ type: 'SET_DISPLAY_MODE', mode: state.displayMode === 'dots' ? 'vehicles' : 'dots' })
          }
          isOverview={isOverview}
          sidebarOpen={state.sidebarOpen}
          sidebarExpanded={state.sidebarExpanded}
          hideFibersInOverview={state.hideFibersInOverview}
          onToggleHideFibers={() => dispatch({ type: 'TOGGLE_HIDE_FIBERS_OVERVIEW' })}
        />

        {/* Toast notifications for new incidents */}
        <IncidentToastStack
          toasts={toasts}
          onClickToast={(incidentId, toastId) => {
            dispatch({ type: 'SELECT_INCIDENT', id: incidentId })
            markSeen(incidentId)
            dismissToast(toastId)
          }}
        />

        {/* Sidebar -- overlays the map from the right */}
        <div className="absolute top-0 right-0 h-full z-20 pointer-events-none">
          <SidePanel
            panelRef={sidebarRef}
            liveStats={liveStats}
            liveSeriesData={liveSeriesData}
            onHighlightFiber={fiberId => mapRef.current?.highlightFiber(fiberId)}
            onHighlightSection={sectionId => mapRef.current?.highlightSection(sectionId)}
            onHighlightIncident={incidentId => mapRef.current?.highlightIncident(incidentId)}
            onClearHighlight={() => mapRef.current?.clearHighlight()}
            infrastructure={infrastructure}
            unseenIds={unseenIds}
            hasUnseen={hasUnseen}
            onMarkSeen={markSeen}
            onMarkAllSeen={markAllSeen}
          />
        </div>

        {/* Naming dialog overlay */}
        {state.showNamingDialog && state.pendingSection && (
          <NamingDialog
            pendingSection={state.pendingSection}
            findFiber={findFiber}
            onSave={async name => {
              const ps = state.pendingSection!
              dispatch({ type: 'CLOSE_NAMING_DIALOG' })
              try {
                const section = await addSection(ps.fiberId, ps.direction, name, ps.startChannel, ps.endChannel)
                dispatch({ type: 'CREATE_SECTION', section })
              } catch {
                toast.error('Failed to create section')
              }
            }}
            onCancel={() => dispatch({ type: 'CLOSE_NAMING_DIALOG' })}
          />
        )}
      </div>
    </SidebarRefContext.Provider>
  )
}

function NamingDialog({
  pendingSection,
  findFiber,
  onSave,
  onCancel,
}: {
  pendingSection: { fiberId: string; direction: 0 | 1; startChannel: number; endChannel: number }
  findFiber: (cableId: string, direction: number) => Fiber | undefined
  onSave: (name: string) => void
  onCancel: () => void
}) {
  const [name, setName] = useState('')
  const fiber = findFiber(pendingSection.fiberId, pendingSection.direction)

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-[var(--dash-surface)] border border-[var(--dash-border)] rounded-lg p-5 w-[360px] shadow-2xl">
        <h3 className="text-sm font-semibold text-[var(--dash-text)] mb-1">Name this section</h3>
        <p className="text-xs text-[var(--dash-text-muted)] mb-4">
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
          className="w-full px-3 py-2 rounded-md bg-[var(--dash-base)] border border-[var(--dash-border)] text-sm text-[var(--dash-text)] placeholder:text-[var(--dash-text-muted)] outline-none focus:border-[var(--dash-accent)] mb-4"
        />
        <div className="flex justify-end gap-2">
          <button
            onClick={onCancel}
            className="px-3 py-1.5 rounded text-xs text-[var(--dash-text-secondary)] hover:text-[var(--dash-text)] transition-colors cursor-pointer"
          >
            Cancel
          </button>
          <button
            onClick={() => name.trim() && onSave(name.trim())}
            disabled={!name.trim()}
            className="px-3 py-1.5 rounded text-xs bg-[var(--dash-accent)] text-white disabled:opacity-40 cursor-pointer hover:bg-[var(--dash-accent)]/80 transition-colors"
          >
            Create
          </button>
        </div>
      </div>
    </div>
  )
}

export default Dashboard
