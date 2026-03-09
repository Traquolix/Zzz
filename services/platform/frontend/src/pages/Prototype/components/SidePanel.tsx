import { useState, useMemo, useEffect, useLayoutEffect, useRef, useCallback, type RefObject } from 'react'
import { createPortal } from 'react-dom'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'
import {
  severityColor,
  fibers,
  getSpeedColor,
  chartColors,
  defaultSpeedThresholds,
  findFiber,
  getFiberColor,
} from '../data'
import { useIncidentSnapshot } from '@/hooks/useIncidentSnapshot'
import type {
  Fiber,
  ProtoIncident,
  ProtoState,
  ProtoAction,
  Severity,
  MetricKey,
  Section,
  LiveSectionStats,
  SectionDataPoint,
  SpeedThresholds,
  SelectedChannel,
} from '../types'
import type {
  Infrastructure,
  SHMStatus,
  SpectralTimeSeries,
  PeakFrequencyData,
  SpectralSummary,
} from '@/types/infrastructure'
import { MAX_SECTIONS_PER_ORG } from '@/api/sections'
import { fetchPeakFrequencies } from '@/api/infrastructure'
import { useRealtime } from '@/hooks/useRealtime'
import { useAuth } from '@/hooks/useAuth'
import { parseDetections } from '@/lib/parseMessage'
import { TimeSeriesChart } from './TimeSeriesChart'
import { Sparkline } from './Sparkline'
import { useWaterfallBuffer } from '../hooks/useWaterfallBuffer'
import { WaterfallCanvas } from './WaterfallCanvas'
import { FlowToggle } from './FlowToggle'
import { useSectionHistory } from '../hooks/useSectionHistory'
import { useDebouncedResize } from '../hooks/useDebouncedResize'
import type { DataFlow } from '@/context/RealtimeContext'

interface StructureDataProp {
  structures: Infrastructure[]
  loading: boolean
  allStatuses: Map<string, SHMStatus>
  shmStatus: SHMStatus | null
  spectralData: SpectralTimeSeries | null
  spectralLoading: boolean
  peakData: PeakFrequencyData | null
  peakLoading: boolean
  dataSummary: SpectralSummary | null
  selectedDay: Date | null
  setSelectedDay: (d: Date | null) => void
}

interface SidePanelProps {
  state: ProtoState
  dispatch: React.Dispatch<ProtoAction>
  liveStats: Map<string, LiveSectionStats>
  liveSeriesData: Map<string, SectionDataPoint[]>
  onHighlightFiber?: (fiberId: string) => void
  onHighlightSection?: (sectionId: string) => void
  onHighlightIncident?: (incidentId: string) => void
  onClearHighlight?: () => void
  structureData?: StructureDataProp
  unseenIds?: Set<string>
  hasUnseen?: boolean
  onMarkSeen?: (id: string) => void
}

const severityOrder: Severity[] = ['critical', 'high', 'medium', 'low']

type TimeRange = '1m' | '5m' | '15m' | '1h'

export function SidePanel({
  state,
  dispatch,
  liveStats,
  liveSeriesData,
  onHighlightFiber,
  onHighlightSection,
  onHighlightIncident,
  onClearHighlight,
  structureData,
  unseenIds,
  hasUnseen,
  onMarkSeen,
}: SidePanelProps) {
  const {
    activeTab,
    selectedIncidentId,
    selectedSectionId,
    selectedStructureId,
    selectedChannel,
    filterSeverity,
    hideResolved,
    sectionMetric,
    sections,
    incidents,
    sidebarOpen,
    sidebarExpanded,
    fiberColors,
    showStructuresOnMap,
    showStructureLabels,
    showIncidentsOnMap,
  } = state
  const realtimeCtx = useRealtime()
  const [incidentSortBy, setIncidentSortBy] = useState<'newest' | 'oldest'>('newest')
  const [shmSearch, setShmSearch] = useState('')
  const [sectionSearch, setSectionSearch] = useState('')

  const incident = selectedIncidentId ? incidents.find(i => i.id === selectedIncidentId) : null
  const section = selectedSectionId ? sections.find(s => s.id === selectedSectionId) : null

  // Track when the slide transition finishes so we can delay showing/hiding elements
  const [, setFullyOpen] = useState(sidebarOpen)
  const [fullyClosed, setFullyClosed] = useState(!sidebarOpen)
  const panelRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (sidebarOpen) {
      setFullyClosed(false)
    } else {
      setFullyOpen(false)
    }
  }, [sidebarOpen])

  const handleTransitionEnd = () => {
    if (sidebarOpen) {
      setFullyOpen(true)
    } else {
      setFullyClosed(true)
    }
  }

  return (
    <div className="relative h-full">
      {/* Collapsed toggle — fixed to top-right, only after panel fully closes */}
      {fullyClosed && !sidebarOpen && (
        <button
          onClick={() => dispatch({ type: 'TOGGLE_SIDEBAR' })}
          className="absolute top-3 right-3 z-30 flex items-center justify-center w-9 h-9 rounded-lg bg-[var(--proto-surface)] border border-[var(--proto-border)] text-[var(--proto-text-muted)] hover:text-[var(--proto-text)] hover:border-[var(--proto-text-muted)]/30 transition-all cursor-pointer pointer-events-auto"
        >
          <SidebarIcon />
          {hasUnseen && (
            <span className="absolute -top-1 -right-1 w-2.5 h-2.5 rounded-full bg-[var(--proto-red)] border-2 border-[var(--proto-surface)]" />
          )}
        </button>
      )}

      {/* Main panel — slides in/out via transform, tabs ride along */}
      <div
        ref={panelRef}
        className={cn(
          'proto-sidebar h-full flex flex-col bg-[var(--proto-surface)] border-l border-[var(--proto-border)] shadow-[-4px_0_16px_rgba(0,0,0,0.3)] pointer-events-auto',
          sidebarExpanded && 'expanded',
        )}
        style={{
          transform: sidebarOpen ? 'translateX(0)' : 'translateX(100%)',
          visibility: fullyClosed && !sidebarOpen ? 'hidden' : 'visible',
        }}
        onTransitionEnd={handleTransitionEnd}
      >
        {/* Floating tab buttons — anchored to the left edge of the panel */}
        <div
          className="absolute top-[28px] bottom-4 flex flex-col justify-between"
          style={{
            right: '100%',
            opacity: sidebarOpen ? 1 : 0,
            transition: sidebarOpen ? 'opacity 150ms 80ms ease-in' : 'opacity 100ms ease-out',
          }}
        >
          <div className="flex flex-col gap-1.5 mt-8">
            <TabButton
              label="Sections"
              icon={<SectionsIcon />}
              active={activeTab === 'sections'}
              onClick={() => dispatch({ type: 'SET_TAB', tab: 'sections' })}
            />
            <TabButton
              label="Incidents"
              icon={<IncidentsIcon />}
              active={activeTab === 'incidents'}
              onClick={() => dispatch({ type: 'SET_TAB', tab: 'incidents' })}
              showDot={hasUnseen}
            />
            <TabButton
              label="SHM"
              icon={<BridgeIcon />}
              active={activeTab === 'shm'}
              onClick={() => dispatch({ type: 'SET_TAB', tab: 'shm' })}
            />
            {/* <TabButton
                            label="Waterfall"
                            icon={<WaterfallIcon />}
                            active={activeTab === 'waterfall'}
                            onClick={() => dispatch({ type: 'SET_TAB', tab: 'waterfall' })}
                        /> */}
          </div>
          <div className="flex flex-col gap-1.5">
            {selectedChannel && (
              <TabButton
                label="Channel"
                icon={<ChannelIcon />}
                active={activeTab === 'channel'}
                onClick={() => dispatch({ type: 'SELECT_CHANNEL', channel: selectedChannel })}
              />
            )}
            <button
              title={sidebarExpanded ? 'Collapse panel' : 'Expand panel'}
              onClick={() => dispatch({ type: 'TOGGLE_SIDEBAR_EXPANDED' })}
              className="group/exp flex items-center justify-center w-[56px] h-5 hover:h-7 rounded-l-lg border border-r-0 border-transparent bg-[var(--proto-surface)]/40 text-[var(--proto-text-muted)] hover:text-[var(--proto-text-secondary)] hover:bg-[var(--proto-surface)]/80 transition-all cursor-pointer"
            >
              <ExpandIcon expanded={!!sidebarExpanded} />
            </button>
            <TabButton
              label="Settings"
              icon={<SettingsIcon />}
              active={activeTab === 'settings'}
              onClick={() => dispatch({ type: 'SET_TAB', tab: 'settings' })}
            />
          </div>
        </div>

        {/* Panel header */}
        <div className="flex items-center justify-between px-4 h-[52px] shrink-0 border-b border-[var(--proto-border)]">
          <div className="flex items-center gap-2.5">
            <span className="text-[length:var(--text-sm)] font-medium text-[var(--proto-text-muted)] uppercase tracking-wider">
              {activeTab}
            </span>
          </div>
          <div className="flex items-center gap-2">
            {activeTab === 'incidents' && (
              <>
                {filterSeverity && (
                  <button
                    onClick={() => dispatch({ type: 'SET_FILTER_SEVERITY', severity: null })}
                    className="w-3 h-3 rounded-full transition-all cursor-pointer opacity-50 hover:opacity-80"
                    style={{ backgroundColor: 'var(--proto-text-muted)' }}
                    title="Clear filter"
                  >
                    <svg
                      width="12"
                      height="12"
                      viewBox="0 0 10 10"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="1.5"
                      strokeLinecap="round"
                      className="text-[var(--proto-surface)]"
                    >
                      <line x1="3" y1="3" x2="7" y2="7" />
                      <line x1="7" y1="3" x2="3" y2="7" />
                    </svg>
                  </button>
                )}
                {severityOrder.map(s => (
                  <button
                    key={s}
                    onClick={() => dispatch({ type: 'SET_FILTER_SEVERITY', severity: filterSeverity === s ? null : s })}
                    className={cn(
                      'w-3 h-3 rounded-full transition-all cursor-pointer ring-offset-1 ring-offset-[var(--proto-surface)]',
                      filterSeverity === s
                        ? 'ring-1 ring-[var(--proto-text-secondary)] scale-125'
                        : 'opacity-50 hover:opacity-80',
                    )}
                    style={{ backgroundColor: severityColor[s] }}
                    title={s.charAt(0).toUpperCase() + s.slice(1)}
                  />
                ))}
                <button
                  onClick={() => dispatch({ type: 'TOGGLE_HIDE_RESOLVED' })}
                  className={cn(
                    'ml-1 flex items-center justify-center w-6 h-6 rounded transition-colors cursor-pointer',
                    hideResolved
                      ? 'text-[var(--proto-text-muted)] hover:text-[var(--proto-text-secondary)]'
                      : 'text-[var(--proto-accent)]',
                  )}
                  title={hideResolved ? 'Show resolved' : 'Hide resolved'}
                >
                  {hideResolved ? (
                    <svg
                      width="14"
                      height="14"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    >
                      <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94" />
                      <path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19" />
                      <line x1="1" y1="1" x2="23" y2="23" />
                    </svg>
                  ) : (
                    <svg
                      width="14"
                      height="14"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    >
                      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
                      <circle cx="12" cy="12" r="3" />
                    </svg>
                  )}
                </button>
                <button
                  onClick={() => dispatch({ type: 'TOGGLE_INCIDENTS_ON_MAP' })}
                  className={cn(
                    'flex items-center justify-center w-6 h-6 rounded transition-colors cursor-pointer',
                    showIncidentsOnMap
                      ? 'text-[var(--proto-accent)]'
                      : 'text-[var(--proto-text-muted)] hover:text-[var(--proto-text-secondary)]',
                  )}
                  title={showIncidentsOnMap ? 'Hide on map' : 'Show on map'}
                >
                  <svg
                    width="14"
                    height="14"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  >
                    <path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7z" />
                    <circle cx="12" cy="9" r="2.5" />
                  </svg>
                </button>
                <button
                  onClick={() => setIncidentSortBy(s => (s === 'newest' ? 'oldest' : 'newest'))}
                  className="flex items-center justify-center w-6 h-6 rounded text-[var(--proto-text-muted)] hover:text-[var(--proto-text)] transition-colors cursor-pointer"
                  title={incidentSortBy === 'newest' ? 'Newest first' : 'Oldest first'}
                >
                  <svg
                    width="12"
                    height="12"
                    viewBox="0 0 12 12"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.2"
                    strokeLinecap="round"
                  >
                    {incidentSortBy === 'newest' ? (
                      <path d="M2 2v8M2 10l-1.5-1.5M2 10l1.5-1.5M6 3h5M6 5.5h3.5M6 8h2" />
                    ) : (
                      <path d="M2 2v8M2 10l-1.5-1.5M2 10l1.5-1.5M6 3h2M6 5.5h3.5M6 8h5" />
                    )}
                  </svg>
                </button>
              </>
            )}
            {activeTab === 'shm' && (
              <>
                <div className="relative">
                  <svg
                    className="absolute left-1.5 top-1/2 -translate-y-1/2 pointer-events-none text-[var(--proto-text-muted)]"
                    width="12"
                    height="12"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2.5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  >
                    <circle cx="11" cy="11" r="8" />
                    <line x1="21" y1="21" x2="16.65" y2="16.65" />
                  </svg>
                  <input
                    type="text"
                    value={shmSearch}
                    onChange={e => setShmSearch(e.target.value)}
                    placeholder="Search..."
                    className="w-28 focus:w-36 pl-5 pr-1.5 py-1 rounded bg-transparent border border-[var(--proto-border)] text-[length:var(--text-xs)] text-[var(--proto-text)] placeholder:text-[var(--proto-text-muted)] outline-none focus:border-[var(--proto-text-secondary)] transition-all"
                  />
                </div>
                <button
                  onClick={() => dispatch({ type: 'TOGGLE_STRUCTURES_ON_MAP' })}
                  className={cn(
                    'flex items-center justify-center w-6 h-6 rounded transition-colors cursor-pointer',
                    showStructuresOnMap
                      ? 'text-[var(--proto-accent)]'
                      : 'text-[var(--proto-text-muted)] hover:text-[var(--proto-text)]',
                  )}
                  title="Show on map"
                >
                  <svg
                    width="14"
                    height="14"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.8"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  >
                    <rect x="1" y="5" width="22" height="14" rx="2" />
                    <path d="M5 5v5" />
                    <path d="M9 5v3" />
                    <path d="M13 5v5" />
                    <path d="M17 5v3" />
                    <path d="M21 5v5" />
                  </svg>
                </button>
                <button
                  onClick={() => dispatch({ type: 'TOGGLE_STRUCTURE_LABELS' })}
                  className={cn(
                    'flex items-center justify-center w-6 h-6 rounded transition-colors cursor-pointer',
                    showStructureLabels
                      ? 'text-[var(--proto-accent)]'
                      : 'text-[var(--proto-text-muted)] hover:text-[var(--proto-text)]',
                  )}
                  title="Show labels"
                >
                  <svg
                    width="14"
                    height="14"
                    viewBox="0 0 14 14"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  >
                    <rect x="1" y="3" width="12" height="8" rx="1.5" />
                    <path d="M4 7h6" />
                    <path d="M4 9.5h3" />
                  </svg>
                </button>
              </>
            )}
            {activeTab === 'sections' && !selectedSectionId && (
              <>
                <div className="relative">
                  <svg
                    className="absolute left-1.5 top-1/2 -translate-y-1/2 pointer-events-none text-[var(--proto-text-muted)]"
                    width="12"
                    height="12"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2.5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  >
                    <circle cx="11" cy="11" r="8" />
                    <line x1="21" y1="21" x2="16.65" y2="16.65" />
                  </svg>
                  <input
                    type="text"
                    value={sectionSearch}
                    onChange={e => setSectionSearch(e.target.value)}
                    placeholder="Search..."
                    className="w-28 focus:w-36 pl-5 pr-1.5 py-1 rounded bg-transparent border border-[var(--proto-border)] text-[length:var(--text-xs)] text-[var(--proto-text)] placeholder:text-[var(--proto-text-muted)] outline-none focus:border-[var(--proto-text-secondary)] transition-all"
                  />
                </div>
                <button
                  onClick={() => dispatch({ type: 'ENTER_SECTION_CREATION' })}
                  disabled={sections.length >= MAX_SECTIONS_PER_ORG}
                  className={cn(
                    'flex items-center justify-center w-6 h-6 rounded transition-colors',
                    sections.length >= MAX_SECTIONS_PER_ORG
                      ? 'text-[var(--proto-text-muted)] opacity-40 cursor-not-allowed'
                      : 'text-[var(--proto-text-muted)] hover:text-[var(--proto-text)] cursor-pointer',
                  )}
                  title={
                    sections.length >= MAX_SECTIONS_PER_ORG
                      ? `Section limit reached (${MAX_SECTIONS_PER_ORG} per organization)`
                      : 'Add section'
                  }
                >
                  <svg
                    width="14"
                    height="14"
                    viewBox="0 0 14 14"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.5"
                    strokeLinecap="round"
                  >
                    <line x1="7" y1="3" x2="7" y2="11" />
                    <line x1="3" y1="7" x2="11" y2="7" />
                  </svg>
                </button>
                <button
                  onClick={() => {
                    const keys = Object.keys(chartColors) as MetricKey[]
                    const idx = keys.indexOf(sectionMetric)
                    dispatch({ type: 'SET_SECTION_METRIC', metric: keys[(idx + 1) % keys.length] })
                  }}
                  className="flex items-center justify-center w-6 h-6 rounded hover:bg-[var(--proto-border)] transition-colors cursor-pointer"
                  title={chartColors[sectionMetric].label}
                >
                  <MetricIcon metric={sectionMetric} />
                </button>
              </>
            )}
            <button
              onClick={() => dispatch({ type: 'TOGGLE_SIDEBAR' })}
              className="flex items-center justify-center w-6 h-6 rounded text-[var(--proto-text-muted)] hover:text-[var(--proto-text)] transition-all cursor-pointer"
            >
              <SidebarIcon />
            </button>
          </div>
        </div>

        {/* Connection status — only show after a connection was established and lost */}
        {realtimeCtx.reconnecting && (
          <div className="px-4 py-1.5 text-[length:var(--text-xs)] text-amber-300 bg-amber-500/10 border-b border-amber-500/20 flex items-center gap-2">
            <svg className="w-3.5 h-3.5 animate-spin" viewBox="0 0 16 16" fill="none">
              <circle cx="8" cy="8" r="6" stroke="currentColor" strokeWidth="2" opacity="0.3" />
              <path d="M14 8a6 6 0 0 0-6-6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
            </svg>
            Reconnecting...
          </div>
        )}

        {/* Content */}
        <div className="flex-1 overflow-y-auto">
          {activeTab === 'incidents' &&
            (incident ? (
              <IncidentDetail
                incident={incident}
                sections={sections}
                dispatch={dispatch}
                onBack={() => dispatch({ type: 'CLEAR_SELECTION' })}
              />
            ) : (
              <IncidentList
                incidents={incidents}
                filterSeverity={filterSeverity}
                hideResolved={hideResolved}
                sortBy={incidentSortBy}
                dispatch={dispatch}
                onHighlightIncident={onHighlightIncident}
                onClearHighlight={onClearHighlight}
                unseenIds={unseenIds}
                onMarkSeen={onMarkSeen}
              />
            ))}
          {activeTab === 'sections' &&
            (section ? (
              <SectionDetail
                section={section}
                onBack={() => dispatch({ type: 'CLEAR_SELECTION' })}
                liveStats={liveStats}
                liveSeriesData={liveSeriesData}
                dispatch={dispatch}
                fiberColors={fiberColors}
              />
            ) : (
              <SectionList
                sections={sections}
                dispatch={dispatch}
                liveStats={liveStats}
                liveSeriesData={liveSeriesData}
                metric={sectionMetric}
                fiberColors={fiberColors}
                onHighlightSection={onHighlightSection}
                onClearHighlight={onClearHighlight}
                search={sectionSearch}
              />
            ))}
          {activeTab === 'settings' && (
            <SettingsPanel
              fiberThresholds={state.fiberThresholds}
              fiberColors={fiberColors}
              dispatch={dispatch}
              onHighlightFiber={onHighlightFiber}
              onClearHighlight={onClearHighlight}
              show3DBuildings={state.show3DBuildings}
              showChannelHelper={state.showChannelHelper}
              flow={realtimeCtx.flow}
              switchingFlow={realtimeCtx.switchingFlow}
              availableFlows={realtimeCtx.availableFlows}
              onFlowToggle={realtimeCtx.setFlow}
            />
          )}
          {activeTab === 'channel' && selectedChannel && (
            <ChannelDetail
              channel={selectedChannel}
              sections={sections}
              dispatch={dispatch}
              fiberColors={fiberColors}
            />
          )}
          {activeTab === 'shm' &&
            structureData &&
            (selectedStructureId ? (
              <StructureDetail
                structure={structureData.structures.find(s => s.id === selectedStructureId) ?? null}
                shmStatus={structureData.shmStatus}
                spectralData={structureData.spectralData}
                spectralLoading={structureData.spectralLoading}
                peakData={structureData.peakData}
                peakLoading={structureData.peakLoading}
                dataSummary={structureData.dataSummary}
                onBack={() => dispatch({ type: 'CLEAR_SELECTION' })}
              />
            ) : (
              <StructureList
                structures={structureData.structures}
                loading={structureData.loading}
                allStatuses={structureData.allStatuses}
                search={shmSearch}
                dispatch={dispatch}
                onHighlightSection={onHighlightSection}
                onClearHighlight={onClearHighlight}
              />
            ))}
          {activeTab === 'waterfall' && <WaterfallPanel />}
        </div>
      </div>
    </div>
  )
}

// ── Tab button ──────────────────────────────────────────────────────────

function TabButton({
  label,
  icon,
  active,
  onClick,
  showDot,
}: {
  label: string
  icon: React.ReactNode
  active: boolean
  onClick: () => void
  showDot?: boolean
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        'relative flex flex-col items-center justify-center gap-1.5 w-[56px] py-3 rounded-l-lg border border-r-0 transition-colors cursor-pointer',
        active
          ? 'bg-[var(--proto-surface)] text-[var(--proto-text)] border-[var(--proto-border)]'
          : 'bg-[var(--proto-surface)]/60 text-[var(--proto-text-muted)] border-transparent hover:text-[var(--proto-text-secondary)] hover:bg-[var(--proto-surface)]/80',
      )}
    >
      {icon}
      <span className="text-[9px] font-medium leading-none">{label}</span>
      {showDot && <span className="absolute top-1.5 right-1.5 w-2 h-2 rounded-full bg-[var(--proto-red)]" />}
    </button>
  )
}

const SidebarIcon = () => (
  <svg
    width="14"
    height="14"
    viewBox="0 0 14 14"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.3"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <rect x="1" y="2" width="12" height="10" rx="1.5" />
    <line x1="9" y1="2" x2="9" y2="12" />
    <rect x="9.5" y="4" width="2.5" height="6" rx="0.5" fill="currentColor" stroke="none" opacity="0.4" />
  </svg>
)

const IncidentsIcon = () => (
  <svg
    width="20"
    height="20"
    viewBox="0 0 16 16"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.5"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <path d="M8 2L14 13H2L8 2Z" />
    <path d="M8 6.5V9" />
    <circle cx="8" cy="11" r="0.5" fill="currentColor" stroke="none" />
  </svg>
)

const SectionsIcon = () => (
  <svg
    width="20"
    height="20"
    viewBox="0 0 16 16"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.5"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <path d="M2 4h12" />
    <path d="M2 8h12" />
    <path d="M2 12h12" />
    <circle cx="4" cy="4" r="1.5" fill="currentColor" stroke="none" />
    <circle cx="12" cy="8" r="1.5" fill="currentColor" stroke="none" />
    <circle cx="7" cy="12" r="1.5" fill="currentColor" stroke="none" />
  </svg>
)

const MetricIcon = ({ metric }: { metric: MetricKey }) => {
  const color = chartColors[metric].color
  if (metric === 'speed')
    return (
      <svg
        width="14"
        height="14"
        viewBox="0 0 24 24"
        fill="none"
        stroke={color}
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d="M12 12l4-4" />
        <path d="M12 22c5.523 0 10-4.477 10-10S17.523 2 12 2 2 6.477 2 12s4.477 10 10 10z" />
      </svg>
    )
  if (metric === 'flow')
    return (
      <svg
        width="14"
        height="14"
        viewBox="0 0 24 24"
        fill="none"
        stroke={color}
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d="M5 12h14" />
        <path d="M12 5l7 7-7 7" />
      </svg>
    )
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke={color}
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <rect x="3" y="12" width="4" height="9" rx="1" />
      <rect x="10" y="7" width="4" height="14" rx="1" />
      <rect x="17" y="3" width="4" height="18" rx="1" />
    </svg>
  )
}

const ExpandIcon = ({ expanded }: { expanded: boolean }) => (
  <svg
    width="12"
    height="12"
    className="group-hover/exp:scale-110 transition-transform"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    {expanded ? (
      <>
        <polyline points="13 17 18 12 13 7" />
        <polyline points="6 17 11 12 6 7" />
      </>
    ) : (
      <>
        <polyline points="11 17 6 12 11 7" />
        <polyline points="18 17 13 12 18 7" />
      </>
    )}
  </svg>
)

const SettingsIcon = () => (
  <svg
    width="20"
    height="20"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.8"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z" />
    <circle cx="12" cy="12" r="3" />
  </svg>
)

const BridgeIcon = () => (
  <svg
    width="20"
    height="20"
    viewBox="0 0 16 16"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.5"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <path d="M1 12h14" />
    <path d="M3 12V7" />
    <path d="M13 12V7" />
    <path d="M3 7C3 7 5.5 4 8 4C10.5 4 13 7 13 7" />
    <path d="M6 12V9" />
    <path d="M10 12V9" />
  </svg>
)

const ChannelIcon = () => (
  <svg
    width="20"
    height="20"
    viewBox="0 0 16 16"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.5"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <circle cx="8" cy="8" r="3" />
    <line x1="8" y1="1" x2="8" y2="4" />
    <line x1="8" y1="12" x2="8" y2="15" />
    <line x1="1" y1="8" x2="4" y2="8" />
    <line x1="12" y1="8" x2="15" y2="8" />
  </svg>
)

/* const WaterfallIcon = () => (
    <svg width="20" height="20" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <rect x="2" y="2" width="12" height="12" rx="1" />
        <line x1="2" y1="6" x2="14" y2="6" opacity="0.3" />
        <line x1="2" y1="10" x2="14" y2="10" opacity="0.3" />
        <circle cx="5" cy="5" r="0.8" fill="currentColor" stroke="none" />
        <circle cx="8" cy="7" r="0.8" fill="currentColor" stroke="none" />
        <circle cx="11" cy="4" r="0.8" fill="currentColor" stroke="none" />
        <circle cx="6" cy="9" r="0.8" fill="currentColor" stroke="none" />
        <circle cx="10" cy="11" r="0.8" fill="currentColor" stroke="none" />
    </svg>
) */

// ── Waterfall panel ─────────────────────────────────────────────────────

function WaterfallPanel() {
  // NOTE: index-based selection assumes `fibers` is a static array.
  // If fibers become dynamic (TTL/hot-reload), switch to keying by fiber ID.
  const [selectedIndex, setSelectedIndex] = useState(0)
  const [windowMs, setWindowMs] = useState(120_000)

  const fiber = fibers[selectedIndex] ?? fibers[0]
  const minChannel = 0
  const maxChannel = (fiber?.totalChannels ?? 500) - 1

  const { dotsRef, dirtyRef, prune, lastTsRef } = useWaterfallBuffer(
    fiber?.parentCableId ?? '',
    fiber?.direction ?? 0,
    windowMs,
  )

  return (
    <div className="flex flex-col h-full">
      {/* Controls */}
      <div className="flex items-center gap-2 px-4 py-2 border-b border-[var(--proto-border)]">
        <select
          value={selectedIndex}
          onChange={e => setSelectedIndex(Number(e.target.value))}
          className="text-[length:var(--text-xs)] px-2 py-1 rounded bg-[var(--proto-base)] border border-[var(--proto-border)] text-[var(--proto-text)] outline-none"
        >
          {fibers.map((f, i) => (
            <option key={f.id} value={i}>
              {f.name}:{f.direction}
            </option>
          ))}
        </select>
        <div className="flex rounded overflow-hidden border border-[var(--proto-border)]">
          {[60_000, 120_000].map(ms => (
            <button
              key={ms}
              onClick={() => setWindowMs(ms)}
              className={cn(
                'text-[length:var(--text-xs)] px-2 py-1 transition-colors cursor-pointer',
                windowMs === ms
                  ? 'bg-[var(--proto-accent)] text-white'
                  : 'bg-[var(--proto-base)] text-[var(--proto-text-muted)] hover:text-[var(--proto-text)]',
              )}
            >
              {ms / 1000}s
            </button>
          ))}
        </div>
      </div>

      {/* Canvas */}
      <div className="flex-1 min-h-0 p-2">
        <WaterfallCanvas
          dotsRef={dotsRef as unknown as RefObject<import('../hooks/useWaterfallBuffer').WaterfallDot[]>}
          dirtyRef={dirtyRef}
          lastTsRef={lastTsRef as unknown as RefObject<number>}
          prune={prune}
          windowMs={windowMs}
          minChannel={minChannel}
          maxChannel={maxChannel}
        />
      </div>

      {/* Speed color legend */}
      <div className="flex items-center gap-3 px-4 py-2 border-t border-[var(--proto-border)]">
        <span className="text-[length:var(--text-2xs)] text-[var(--proto-text-muted)]">Speed:</span>
        {[
          { color: '#22c55e', label: '≥80' },
          { color: '#eab308', label: '≥60' },
          { color: '#f97316', label: '≥30' },
          { color: '#ef4444', label: '<30' },
        ].map(({ color, label }) => (
          <div key={label} className="flex items-center gap-1">
            <span className="w-2.5 h-2.5 rounded-sm" style={{ backgroundColor: color }} />
            <span className="text-[length:var(--text-2xs)] text-[var(--proto-text-muted)]">{label}</span>
          </div>
        ))}
        <span className="text-[length:var(--text-2xs)] text-[var(--proto-text-muted)] ml-auto">km/h</span>
      </div>
    </div>
  )
}

// ── Channel detail ──────────────────────────────────────────────────────

function ChannelDetail({
  channel,
  sections,
  dispatch,
  fiberColors,
}: {
  channel: SelectedChannel
  sections: Section[]
  dispatch: React.Dispatch<ProtoAction>
  fiberColors: Record<string, string>
}) {
  const fiber = findFiber(channel.fiberId, channel.direction)
  const fiberColor = fiber ? getFiberColor(fiber, fiberColors) : '#6366f1'
  const directionLabel = fiber?.direction === 0 ? 'Dir A' : 'Dir B'

  // Find sections containing this channel
  const containingSections = sections.filter(
    s =>
      s.fiberId === channel.fiberId &&
      s.direction === channel.direction &&
      channel.channel >= s.startChannel &&
      channel.channel <= s.endChannel,
  )

  // Live speed data from WebSocket
  const { subscribe } = useRealtime()
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const dotsRef = useRef<{ time: number; speed: number }[]>([])
  const statsRef = useRef({ count: 0, speedSum: 0 })
  const [liveCount, setLiveCount] = useState(0)
  const [liveAvgSpeed, setLiveAvgSpeed] = useState<number | null>(null)

  // Reset on channel change
  useEffect(() => {
    dotsRef.current = []
    statsRef.current = { count: 0, speedSum: 0 }
    setLiveCount(0)
    setLiveAvgSpeed(null)
  }, [channel.fiberId, channel.channel])

  // Subscribe to detections and collect speed dots
  useEffect(() => {
    const NEIGHBOR_RANGE = 0

    const unsub = subscribe('detections', (data: unknown) => {
      const detections = parseDetections(data)
      const now = Date.now()

      for (const d of detections) {
        if (d.fiberId !== channel.fiberId || d.direction !== channel.direction) continue
        if (Math.abs(d.channel - channel.channel) > NEIGHBOR_RANGE) continue
        dotsRef.current.push({ time: now, speed: d.speed })
      }
    })
    return unsub
  }, [subscribe, channel.fiberId, channel.direction, channel.channel])

  // Canvas render loop + stats update
  useEffect(() => {
    let rafId: number
    const WINDOW_MS = 60_000 // 60s rolling window
    const STATS_WINDOW_MS = 10_000 // 10s for stats

    function render() {
      const canvas = canvasRef.current
      if (!canvas) {
        rafId = requestAnimationFrame(render)
        return
      }
      const ctx = canvas.getContext('2d')
      if (!ctx) {
        rafId = requestAnimationFrame(render)
        return
      }

      const now = Date.now()
      const cutoff = now - WINDOW_MS
      const statsCutoff = now - STATS_WINDOW_MS

      // Prune old dots
      while (dotsRef.current.length > 0 && dotsRef.current[0].time < cutoff) {
        dotsRef.current.shift()
      }

      // Compute stats (last 10s)
      let count = 0
      let speedSum = 0
      for (const dot of dotsRef.current) {
        if (dot.time >= statsCutoff) {
          count++
          speedSum += dot.speed
        }
      }
      statsRef.current = { count, speedSum }

      const dpr = window.devicePixelRatio || 1
      const w = canvas.clientWidth
      const h = canvas.clientHeight
      canvas.width = w * dpr
      canvas.height = h * dpr
      ctx.scale(dpr, dpr)

      // Clear (transparent — panel background shows through)
      ctx.clearRect(0, 0, w, h)

      // Grid lines
      const maxSpeed = 140
      ctx.strokeStyle = 'rgba(148, 163, 184, 0.1)'
      ctx.lineWidth = 1
      for (const spd of [0, 30, 60, 90, 120]) {
        const y = h - (spd / maxSpeed) * h
        ctx.beginPath()
        ctx.moveTo(0, y)
        ctx.lineTo(w, y)
        ctx.stroke()
      }

      // Y-axis labels
      ctx.fillStyle = 'rgba(148, 163, 184, 0.4)'
      ctx.font = '9px monospace'
      ctx.textAlign = 'left'
      for (const spd of [30, 60, 90, 120]) {
        const y = h - (spd / maxSpeed) * h
        ctx.fillText(`${spd}`, 2, y - 2)
      }

      // Draw dots
      for (const dot of dotsRef.current) {
        const x = ((dot.time - cutoff) / WINDOW_MS) * w
        const y = h - (Math.min(dot.speed, maxSpeed) / maxSpeed) * h
        const age = (now - dot.time) / WINDOW_MS
        const alpha = 1 - age * 0.7

        ctx.globalAlpha = alpha
        ctx.beginPath()
        ctx.arc(x, y, 2.5, 0, Math.PI * 2)
        ctx.fillStyle = getSpeedColor(dot.speed)
        ctx.fill()
      }
      ctx.globalAlpha = 1

      rafId = requestAnimationFrame(render)
    }

    rafId = requestAnimationFrame(render)
    return () => cancelAnimationFrame(rafId)
  }, [channel.fiberId, channel.channel])

  // Stats update at 2Hz
  useEffect(() => {
    const timer = setInterval(() => {
      const { count, speedSum } = statsRef.current
      setLiveCount(count)
      setLiveAvgSpeed(count > 0 ? Math.round(speedSum / count) : null)
    }, 500)
    return () => clearInterval(timer)
  }, [])

  const speedColor = liveAvgSpeed != null ? getSpeedColor(liveAvgSpeed) : undefined

  return (
    <div className="proto-analysis-enter flex flex-col">
      {/* Header — matching SectionDetail pattern */}
      <div className="sticky top-0 z-10 bg-[var(--proto-surface)] border-b border-[var(--proto-border)] px-4 py-3">
        <div className="min-w-0">
          <span className="text-[length:var(--text-sm)] font-semibold text-[var(--proto-text)] truncate block">
            Channel {channel.channel}
          </span>
          <span className="text-[length:var(--text-2xs)] text-[var(--proto-text-muted)] flex items-center gap-1.5">
            <span className="inline-block w-2 h-2 rounded-full flex-shrink-0" style={{ backgroundColor: fiberColor }} />
            {fiber?.name ?? channel.fiberId} · {directionLabel} · {channel.lat.toFixed(5)}N, {channel.lng.toFixed(5)}E
          </span>
        </div>
      </div>

      <div className="px-4 py-4 flex flex-col gap-3">
        {/* KPI cards — 2-column grid */}
        <div className="grid grid-cols-2 gap-3">
          <div className="rounded-lg border border-[var(--proto-border)] p-3">
            <div className="text-[length:var(--text-2xs)] text-[var(--proto-text-muted)] uppercase tracking-wider mb-1">
              Detections
            </div>
            <div>
              <span className="text-[length:var(--text-xl)] font-semibold text-[var(--proto-text)]">{liveCount}</span>
              <span className="text-[length:var(--text-xs)] text-[var(--proto-text-muted)] ml-1">in 10s</span>
            </div>
          </div>
          <div className="rounded-lg border border-[var(--proto-border)] p-3">
            <div className="text-[length:var(--text-2xs)] text-[var(--proto-text-muted)] uppercase tracking-wider mb-1">
              Avg Speed
            </div>
            <div>
              <span
                className="text-[length:var(--text-xl)] font-semibold"
                style={{ color: speedColor ?? 'var(--proto-text)' }}
              >
                {liveAvgSpeed != null ? liveAvgSpeed : '\u2014'}
              </span>
              <span className="text-[length:var(--text-xs)] text-[var(--proto-text-muted)] ml-1">km/h</span>
            </div>
          </div>
        </div>

        {/* Live speed chart */}
        <div className="rounded-lg border border-[var(--proto-border)] overflow-hidden">
          <div className="px-3 py-2 flex items-center justify-between">
            <h3 className="text-[length:var(--text-2xs)] font-medium text-[var(--proto-text-muted)] uppercase tracking-wider">
              Live Speed
            </h3>
            <span className="text-[length:var(--text-2xs)] text-[var(--proto-text-muted)]">(60s)</span>
          </div>
          <canvas ref={canvasRef} className="w-full" style={{ height: 160, borderRadius: '0 0 8px 8px' }} />
        </div>

        {/* Containing sections */}
        <div>
          <h3 className="text-[length:var(--text-2xs)] font-medium text-[var(--proto-text-muted)] uppercase tracking-wider mb-2">
            Sections
          </h3>
          {containingSections.length > 0 ? (
            <div className="flex flex-col gap-1.5">
              {containingSections.map(sec => {
                const secFiber = findFiber(sec.fiberId, sec.direction)
                const secColor = secFiber ? getFiberColor(secFiber, fiberColors) : '#888'
                return (
                  <button
                    key={sec.id}
                    onClick={() => dispatch({ type: 'SELECT_SECTION', id: sec.id })}
                    className="flex items-center gap-2.5 w-full text-left rounded-lg border border-[var(--proto-border)] px-3 py-2 hover:bg-[var(--proto-surface-raised)] transition-colors cursor-pointer"
                  >
                    <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ backgroundColor: secColor }} />
                    <span className="text-[length:var(--text-sm)] text-[var(--proto-text)] truncate flex-1">
                      {sec.name}
                    </span>
                    <span className="text-[length:var(--text-2xs)] text-[var(--proto-text-muted)] flex-shrink-0 px-1.5 py-0.5 rounded bg-[var(--proto-base)]">
                      Ch {sec.startChannel}–{sec.endChannel}
                    </span>
                  </button>
                )
              })}
            </div>
          ) : (
            <p className="text-[length:var(--text-xs)] text-[var(--proto-text-muted)] italic">
              No sections contain this channel
            </p>
          )}
        </div>
      </div>
    </div>
  )
}

// ── Incident list ───────────────────────────────────────────────────────

function IncidentList({
  incidents,
  filterSeverity,
  hideResolved,
  sortBy,
  dispatch,
  onHighlightIncident,
  onClearHighlight,
  unseenIds,
  onMarkSeen,
}: {
  incidents: ProtoIncident[]
  filterSeverity: Severity | null
  hideResolved: boolean
  sortBy: 'newest' | 'oldest'
  dispatch: React.Dispatch<ProtoAction>
  onHighlightIncident?: (id: string) => void
  onClearHighlight?: () => void
  unseenIds?: Set<string>
  onMarkSeen?: (id: string) => void
}) {
  let filtered = filterSeverity ? incidents.filter(i => i.severity === filterSeverity) : incidents
  if (hideResolved) filtered = filtered.filter(i => !i.resolved)

  const sorted = [...filtered].sort((a, b) => {
    const ta = new Date(a.detectedAt).getTime()
    const tb = new Date(b.detectedAt).getTime()
    return sortBy === 'newest' ? tb - ta : ta - tb
  })

  return (
    <>
      {sorted.length === 0 ? (
        <div className="flex items-center justify-center h-32 text-[var(--proto-text-muted)] text-[length:var(--text-sm)]">
          No incidents match this filter
        </div>
      ) : (
        <div className="flex flex-col px-3 py-1">
          {sorted.map(inc => (
            <button
              key={inc.id}
              onClick={() => dispatch({ type: 'SELECT_INCIDENT', id: inc.id })}
              onMouseEnter={() => {
                onHighlightIncident?.(inc.id)
                onMarkSeen?.(inc.id)
              }}
              onMouseLeave={() => onClearHighlight?.()}
              className="w-full text-left px-3 py-2.5 rounded-lg hover:bg-[var(--proto-surface-raised)] transition-colors cursor-pointer"
            >
              <div className="flex items-start gap-2.5 min-w-0">
                <span
                  className="shrink-0 w-2 h-2 rounded-full mt-1.5"
                  style={{ backgroundColor: severityColor[inc.severity] }}
                />
                {unseenIds?.has(inc.id) && (
                  <span className="shrink-0 w-1.5 h-1.5 rounded-full bg-[var(--proto-accent)] mt-2 -ml-1.5" />
                )}
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-[length:var(--text-sm)] text-[var(--proto-text)] font-medium truncate">
                      {inc.title}
                    </span>
                    <span className="shrink-0 text-[length:var(--text-xs)] tabular-nums text-[var(--proto-text-secondary)]">
                      {new Date(inc.detectedAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </span>
                  </div>
                  <div className="flex items-center gap-1.5 text-[length:var(--text-xxs)] text-[var(--proto-text-muted)] mt-0.5">
                    <span>
                      Ch {inc.channel}
                      {inc.channelEnd && inc.channelEnd !== inc.channel ? `–${inc.channelEnd}` : ''}
                    </span>
                    <span className="opacity-40">·</span>
                    <span>{new Date(inc.detectedAt).toLocaleDateString([], { day: 'numeric', month: 'short' })}</span>
                    {inc.resolved && (
                      <>
                        <span className="opacity-40">·</span>
                        <span className="text-[var(--proto-green)]">resolved</span>
                      </>
                    )}
                  </div>
                </div>
              </div>
            </button>
          ))}
        </div>
      )}
    </>
  )
}

// ── Section list ────────────────────────────────────────────────────────

function SectionList({
  sections,
  dispatch,
  liveStats,
  liveSeriesData,
  metric,
  fiberColors,
  onHighlightSection,
  onClearHighlight,
  search,
}: {
  sections: Section[]
  dispatch: React.Dispatch<ProtoAction>
  liveStats: Map<string, LiveSectionStats>
  liveSeriesData: Map<string, SectionDataPoint[]>
  metric: MetricKey
  fiberColors: Record<string, string>
  onHighlightSection?: (id: string) => void
  onClearHighlight?: () => void
  search?: string
}) {
  const metricConfig = chartColors[metric]
  const query = search?.trim().toLowerCase() ?? ''
  const filtered = query
    ? sections.filter(s => s.name.toLowerCase().includes(query) || s.fiberId.toLowerCase().includes(query))
    : sections

  return (
    <>
      {sections.length === 0 ? (
        <div className="flex items-center justify-center h-32 text-[var(--proto-text-muted)] text-[length:var(--text-sm)]">
          No sections yet
        </div>
      ) : filtered.length === 0 ? (
        <div className="flex items-center justify-center h-32 text-[var(--proto-text-muted)] text-[length:var(--text-sm)]">
          No matching sections
        </div>
      ) : (
        <div className="flex flex-col px-3 py-1">
          {filtered.map(section => {
            const fiber = findFiber(section.fiberId, section.direction)
            const live = liveStats.get(section.id)
            const liveSeries = liveSeriesData.get(section.id)

            // Derive values based on selected metric
            const SPARK_LENGTH = 30
            let displayValue: number
            let spark: number[]

            if (metric === 'speed') {
              displayValue = live?.avgSpeed != null ? Math.round(live.avgSpeed) : section.avgSpeed
              spark = liveSeries?.length ? liveSeries.slice(-SPARK_LENGTH).map(p => p.speed) : section.speedHistory
            } else if (metric === 'flow') {
              displayValue = live?.flow ?? section.flow
              spark = liveSeries?.length ? liveSeries.slice(-SPARK_LENGTH).map(p => p.flow) : section.countHistory
            } else {
              displayValue = live?.occupancy ?? section.occupancy
              spark = liveSeries?.length ? liveSeries.slice(-SPARK_LENGTH).map(p => p.occupancy) : []
            }

            const trend = computeTrend(spark)

            return (
              <div key={section.id} className="group relative">
                <button
                  onClick={() => dispatch({ type: 'SELECT_SECTION', id: section.id })}
                  onMouseEnter={() => onHighlightSection?.(section.id)}
                  onMouseLeave={() => onClearHighlight?.()}
                  className="w-full text-left px-3 py-2.5 rounded-lg hover:bg-[var(--proto-surface-raised)] transition-colors cursor-pointer"
                >
                  <div className="flex items-center gap-2 mb-1">
                    <span
                      className="shrink-0 w-2 h-2 rounded-full"
                      style={{ backgroundColor: fiber ? getFiberColor(fiber, fiberColors) : undefined }}
                    />
                    <span className="text-[length:var(--text-sm)] text-[var(--proto-text)] font-medium truncate">
                      {section.name}
                    </span>
                  </div>
                  <div className="flex items-center justify-between text-[length:var(--text-xs)] text-[var(--proto-text-secondary)] pl-4">
                    <span>
                      <span
                        style={{
                          color:
                            metric === 'speed'
                              ? getSpeedColor(displayValue, section.speedThresholds)
                              : metricConfig.color,
                        }}
                      >
                        {displayValue}
                      </span>{' '}
                      {metricConfig.unit}
                      <TrendBadge pct={trend.pct} positiveIsGood={metric !== 'occupancy'} />
                    </span>
                    {spark.length > 0 && (
                      <div className="shrink-0 pr-1 overflow-hidden">
                        <Sparkline data={spark} color={metricConfig.color} width={56} height={16} />
                      </div>
                    )}
                  </div>
                </button>
                <button
                  onClick={e => {
                    e.stopPropagation()
                    dispatch({ type: 'DELETE_SECTION', id: section.id })
                  }}
                  className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 text-[var(--proto-text-muted)] hover:text-[var(--proto-red)] transition-all text-[length:var(--text-xs)] cursor-pointer px-1"
                >
                  &times;
                </button>
              </div>
            )
          })}
        </div>
      )}
    </>
  )
}

// ── Incident detail ─────────────────────────────────────────────────────

function IncidentDetail({
  incident,
  sections,
  dispatch,
  onBack,
}: {
  incident: ProtoIncident
  sections: Section[]
  dispatch: React.Dispatch<ProtoAction>
  onBack: () => void
}) {
  const { flow } = useRealtime()

  // Find containing section by channel range
  const relatedSection = sections.find(
    s =>
      s.fiberId === incident.fiberId &&
      s.direction === incident.direction &&
      incident.channel >= s.startChannel &&
      incident.channel <= s.endChannel,
  )

  // Fetch snapshot data from API — polls every 1s until snapshot is complete
  const {
    points: snapshotData,
    loading: snapshotLoading,
    complete: snapshotComplete,
  } = useIncidentSnapshot(incident.id, flow)

  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(incident.description)

  return (
    <div className="proto-analysis-enter flex flex-col">
      <div className="sticky top-0 z-10 bg-[var(--proto-surface)] border-b border-[var(--proto-border)] px-4 py-3 flex items-center gap-3">
        <button
          onClick={onBack}
          className="text-[var(--proto-text-muted)] hover:text-[var(--proto-text)] transition-colors text-[length:var(--text-sm)] cursor-pointer"
        >
          &larr; Back
        </button>
        <span className="text-[length:var(--text-sm)] font-semibold text-[var(--proto-text)] truncate">
          {incident.title}
        </span>
        <span
          className="text-[length:var(--text-2xs)] font-medium px-1.5 py-0.5 rounded capitalize shrink-0"
          style={{ backgroundColor: `${severityColor[incident.severity]}20`, color: severityColor[incident.severity] }}
        >
          {incident.severity}
        </span>
      </div>

      <div className="px-4 py-4 flex flex-col gap-3">
        {/* Speed metrics when available */}
        {(incident.speedBefore != null || incident.speedDuring != null) && (
          <div className="grid grid-cols-3 gap-2 pb-3 border-b border-[var(--proto-border)]">
            {incident.speedBefore != null && (
              <div className="rounded-lg border border-[var(--proto-border)] p-2.5">
                <div className="text-[length:var(--text-2xs)] text-[var(--proto-text-muted)] uppercase tracking-wider mb-0.5">
                  Before
                </div>
                <span className="text-[length:var(--text-lg)] font-semibold text-[var(--proto-text)]">
                  {Math.round(incident.speedBefore)}
                </span>
                <span className="text-[length:var(--text-2xs)] text-[var(--proto-text-muted)] ml-0.5">km/h</span>
              </div>
            )}
            {incident.speedDuring != null && (
              <div className="rounded-lg border border-[var(--proto-border)] p-2.5">
                <div className="text-[length:var(--text-2xs)] text-[var(--proto-text-muted)] uppercase tracking-wider mb-0.5">
                  During
                </div>
                <span className="text-[length:var(--text-lg)] font-semibold text-[var(--proto-red)]">
                  {Math.round(incident.speedDuring)}
                </span>
                <span className="text-[length:var(--text-2xs)] text-[var(--proto-text-muted)] ml-0.5">km/h</span>
              </div>
            )}
            {incident.speedDropPercent != null && (
              <div className="rounded-lg border border-[var(--proto-border)] p-2.5">
                <div className="text-[length:var(--text-2xs)] text-[var(--proto-text-muted)] uppercase tracking-wider mb-0.5">
                  Drop
                </div>
                <span className="text-[length:var(--text-lg)] font-semibold text-[var(--proto-red)]">
                  {Math.round(incident.speedDropPercent)}
                </span>
                <span className="text-[length:var(--text-2xs)] text-[var(--proto-text-muted)] ml-0.5">%</span>
              </div>
            )}
          </div>
        )}

        <div className="pb-3 border-b border-[var(--proto-border)]">
          {editing ? (
            <div className="flex flex-col gap-2">
              <textarea
                autoFocus
                value={draft}
                onChange={e => setDraft(e.target.value)}
                rows={3}
                className="w-full px-2 py-1.5 rounded bg-[var(--proto-surface)] border border-[var(--proto-border)] text-[length:var(--text-sm)] text-[var(--proto-text)] outline-none focus:border-[var(--proto-accent)] resize-none"
              />
              <div className="flex gap-2 justify-end">
                <button
                  onClick={() => {
                    setDraft(incident.description)
                    setEditing(false)
                  }}
                  className="px-2 py-1 rounded text-[length:var(--text-xs)] text-[var(--proto-text-muted)] hover:text-[var(--proto-text)] transition-colors cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  onClick={() => {
                    dispatch({ type: 'UPDATE_INCIDENT_DESCRIPTION', id: incident.id, description: draft })
                    setEditing(false)
                  }}
                  className="px-2 py-1 rounded text-[length:var(--text-xs)] bg-[var(--proto-accent)] text-white cursor-pointer hover:opacity-80 transition-opacity"
                >
                  Save
                </button>
              </div>
            </div>
          ) : (
            <div
              className="text-[length:var(--text-sm)] text-[var(--proto-text)] mb-2 cursor-pointer hover:bg-[var(--proto-surface-raised)] rounded px-1 -mx-1 py-0.5 transition-colors"
              onClick={() => {
                setDraft(incident.description)
                setEditing(true)
              }}
              title="Click to edit"
            >
              {incident.description}
            </div>
          )}
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-[length:var(--text-xs)] text-[var(--proto-text-secondary)]">
            <span>
              Type: <span className="capitalize">{incident.type}</span>
            </span>
            <span>
              Time: {new Date(incident.detectedAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
            </span>
            <span>
              Location: {incident.location[1].toFixed(4)}N, {incident.location[0].toFixed(4)}E
            </span>
            <span>
              Channel: {incident.channel}
              {incident.channelEnd != null && incident.channelEnd !== incident.channel ? `–${incident.channelEnd}` : ''}
            </span>
            <span>
              Status:{' '}
              <span className={cn(incident.resolved ? 'text-[var(--proto-green)]' : 'text-[var(--proto-red)]')}>
                {incident.resolved ? 'Resolved' : 'Active'}
              </span>
            </span>
          </div>
        </div>

        {relatedSection && (
          <div className="pb-3 border-b border-[var(--proto-border)]">
            <h3 className="text-[length:var(--text-xs)] font-medium text-[var(--proto-text-muted)] uppercase tracking-wider mb-2">
              Affected Section
            </h3>
            <div className="text-[length:var(--text-sm)] text-[var(--proto-text)] mb-1">{relatedSection.name}</div>
            <div className="flex gap-4 text-[length:var(--text-xs)] text-[var(--proto-text-secondary)]">
              <span>{relatedSection.avgSpeed} km/h</span>
              <span>{relatedSection.flow} veh/h</span>
              <span>{relatedSection.occupancy}% occ.</span>
              <span>
                Ch {relatedSection.startChannel}-{relatedSection.endChannel}
              </span>
            </div>
          </div>
        )}

        <div>
          <h3 className="text-[length:var(--text-xs)] font-medium text-[var(--proto-text-muted)] uppercase tracking-wider mb-3">
            Snapshot
            {!snapshotComplete && !snapshotLoading && (
              <span className="ml-2 text-[var(--proto-accent)] animate-pulse">collecting...</span>
            )}
          </h3>
          {snapshotLoading ? (
            <div className="h-[200px] rounded bg-[var(--proto-surface)] animate-pulse flex items-center justify-center">
              <span className="text-[length:var(--text-xs)] text-[var(--proto-text-muted)]">Loading snapshot...</span>
            </div>
          ) : snapshotData ? (
            <TimeSeriesChart
              data={snapshotData}
              incidentTime={new Date(incident.detectedAt).toLocaleTimeString([], {
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit',
                hour12: false,
              })}
            />
          ) : (
            <div className="text-[length:var(--text-xs)] text-[var(--proto-text-muted)] italic py-4 text-center">
              No snapshot data available
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ── Section detail ──────────────────────────────────────────────────────

function computeTrend(history: number[]): { pct: number } {
  if (history.length < 10) return { pct: 0 }
  const recent = history.slice(-5)
  const earlier = history.slice(0, 5)
  const avgRecent = recent.reduce((a, b) => a + b, 0) / recent.length
  const avgEarlier = earlier.reduce((a, b) => a + b, 0) / earlier.length
  const delta = avgRecent - avgEarlier
  const pct = avgEarlier !== 0 ? Math.round((delta / avgEarlier) * 100) : 0
  return { pct }
}

function TrendBadge({ pct, positiveIsGood }: { pct: number; positiveIsGood: boolean }) {
  if (pct === 0) return null
  const isUp = pct > 0
  const isGood = positiveIsGood ? isUp : !isUp
  return (
    <span className={cn('text-[length:var(--text-2xs)] ml-1', isGood ? 'text-green-400' : 'text-red-400')}>
      {isUp ? '\u2191' : '\u2193'}
      {Math.abs(pct)}%
    </span>
  )
}

function ThresholdEditor({
  thresholds,
  onChange,
}: {
  thresholds: SpeedThresholds
  onChange: (t: SpeedThresholds) => void
}) {
  const [draft, setDraft] = useState<SpeedThresholds>(thresholds)
  const isDirty =
    draft.green !== thresholds.green || draft.yellow !== thresholds.yellow || draft.orange !== thresholds.orange

  // Sync draft when thresholds change externally (e.g. switching sections)
  useEffect(() => {
    setDraft(thresholds)
    // eslint-disable-next-line react-hooks/exhaustive-deps -- list individual fields to avoid re-render when object ref changes but values are the same
  }, [thresholds.green, thresholds.yellow, thresholds.orange])

  const fields: { key: keyof SpeedThresholds; label: string; color: string }[] = [
    { key: 'green', label: 'Green', color: '#22c55e' },
    { key: 'yellow', label: 'Yellow', color: '#eab308' },
    { key: 'orange', label: 'Orange', color: '#f97316' },
  ]

  return (
    <div className="border-t border-[var(--proto-border)] pt-3">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-[length:var(--text-xs)] font-medium text-[var(--proto-text-muted)] uppercase tracking-wider">
          Speed Thresholds
        </h3>
        {isDirty && (
          <button
            onClick={() => onChange(draft)}
            className="px-2.5 py-1 rounded text-[length:var(--text-2xs)] font-medium bg-[var(--proto-accent)] text-white cursor-pointer hover:opacity-80 transition-opacity"
          >
            Apply
          </button>
        )}
      </div>
      <div className="flex gap-5">
        {fields.map(f => (
          <label key={f.key} className="flex items-center gap-2">
            <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ backgroundColor: f.color }} />
            <input
              type="number"
              value={draft[f.key]}
              onChange={e => {
                const val = parseInt(e.target.value, 10)
                if (!isNaN(val) && val >= 0) {
                  setDraft(prev => ({ ...prev, [f.key]: val }))
                }
              }}
              className="w-12 px-1 py-0.5 rounded bg-transparent border border-[var(--proto-border)] text-[length:var(--text-xs)] text-[var(--proto-text)] text-center outline-none focus:border-[var(--proto-text-secondary)] [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
            />
            <span className="text-[length:var(--text-2xs)] text-[var(--proto-text-muted)]">km/h</span>
          </label>
        ))}
      </div>
    </div>
  )
}

// ── Settings panel ──────────────────────────────────────────────────────

const FIBER_COLOR_PALETTE = [
  '#6366f1',
  '#818cf8',
  '#8b5cf6',
  '#a78bfa',
  '#0ea5e9',
  '#38bdf8',
  '#06b6d4',
  '#22d3ee',
  '#10b981',
  '#34d399',
  '#22c55e',
  '#4ade80',
  '#f59e0b',
  '#fbbf24',
  '#f97316',
  '#fb923c',
  '#ef4444',
  '#f87171',
  '#ec4899',
  '#f472b6',
  '#64748b',
  '#94a3b8',
  '#e2e8f0',
  '#ffffff',
]

function ColorPicker({
  current,
  onSelect,
  onClose,
  anchorRef,
}: {
  current: string
  onSelect: (c: string) => void
  onClose: () => void
  anchorRef?: React.RefObject<HTMLElement | null>
}) {
  const ref = useRef<HTMLDivElement>(null)
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null)
  const readyRef = useRef(false)

  useLayoutEffect(() => {
    if (!anchorRef?.current) return
    const rect = anchorRef.current.getBoundingClientRect()
    const pickerHeight = 4 * (20 + 6) + 16
    let top = rect.top - pickerHeight - 8
    if (top < 8) top = rect.bottom + 8
    setPos({ top, left: rect.left })
  }, [anchorRef])

  // Mark ready after a frame so the opening click doesn't immediately close
  useEffect(() => {
    const id = requestAnimationFrame(() => {
      readyRef.current = true
    })
    return () => cancelAnimationFrame(id)
  }, [])

  useEffect(() => {
    function handler(e: MouseEvent) {
      if (!readyRef.current) return
      if (ref.current && !ref.current.contains(e.target as Node)) {
        onClose()
      }
    }
    document.addEventListener('mousedown', handler, true)
    return () => document.removeEventListener('mousedown', handler, true)
  }, [onClose])

  if (!pos) return null

  return createPortal(
    <div ref={ref} className="prototype" style={{ position: 'fixed', zIndex: 9999, top: pos.top, left: pos.left }}>
      <div className="p-2 rounded-lg bg-[var(--proto-surface-raised)] border border-[var(--proto-border)] shadow-xl grid grid-cols-6 gap-1.5">
        {FIBER_COLOR_PALETTE.map(c => (
          <button
            key={c}
            onClick={() => {
              onSelect(c)
              onClose()
            }}
            className={cn(
              'w-5 h-5 rounded-full cursor-pointer transition-transform hover:scale-125',
              c === current && 'ring-2 ring-white ring-offset-1 ring-offset-[var(--proto-surface-raised)]',
            )}
            style={{ backgroundColor: c }}
          />
        ))}
      </div>
    </div>,
    document.body,
  )
}

function FiberColorDot({
  direction,
  color,
  isPickerOpen,
  onTogglePicker,
  onSelect,
  onClosePicker,
  onMouseEnter,
  onMouseLeave,
}: {
  direction: 0 | 1
  color: string
  isPickerOpen: boolean
  onTogglePicker: () => void
  onSelect: (c: string) => void
  onClosePicker: () => void
  onMouseEnter: () => void
  onMouseLeave: () => void
}) {
  const btnRef = useRef<HTMLButtonElement>(null)
  const dirLabel = direction === 0 ? 'Dir A' : 'Dir B'

  return (
    <div className="flex items-center gap-1.5" onMouseEnter={onMouseEnter} onMouseLeave={onMouseLeave}>
      <button
        ref={btnRef}
        onClick={onTogglePicker}
        className="w-3 h-3 rounded-full shrink-0 cursor-pointer ring-offset-1 ring-offset-[var(--proto-surface)] hover:ring-1 hover:ring-[var(--proto-text-muted)] transition-all"
        style={{ backgroundColor: color }}
        title={`Change ${dirLabel} color`}
      />
      <span className="text-[length:var(--text-2xs)] text-[var(--proto-text-muted)]">{dirLabel}</span>
      {isPickerOpen && <ColorPicker current={color} onSelect={onSelect} onClose={onClosePicker} anchorRef={btnRef} />}
    </div>
  )
}

function SettingsPanel({
  fiberThresholds,
  fiberColors,
  dispatch,
  onHighlightFiber,
  onClearHighlight,
  show3DBuildings,
  showChannelHelper,
  flow,
  switchingFlow,
  availableFlows,
  onFlowToggle,
}: {
  fiberThresholds: Record<string, SpeedThresholds>
  fiberColors: Record<string, string>
  dispatch: React.Dispatch<ProtoAction>
  onHighlightFiber?: (fiberId: string) => void
  onClearHighlight?: () => void
  show3DBuildings: boolean
  showChannelHelper: boolean
  flow: DataFlow
  switchingFlow: boolean
  availableFlows: DataFlow[]
  onFlowToggle: (flow: DataFlow) => void
}) {
  const { t } = useTranslation()
  const [colorPickerOpen, setColorPickerOpen] = useState<string | null>(null)

  // Group fibers by cable
  const cableGroups = useMemo(() => {
    const map = new Map<string, { name: string; fibers: Fiber[] }>()
    for (const f of fibers) {
      let group = map.get(f.parentCableId)
      if (!group) {
        group = { name: f.name, fibers: [] }
        map.set(f.parentCableId, group)
      }
      group.fibers.push(f)
    }
    return [...map.entries()]
  }, [])

  return (
    <div className="px-4 py-4 flex flex-col gap-5">
      {/* Data source */}
      <div className="flex flex-col gap-2">
        <span className="text-[length:var(--text-xs)] text-[var(--proto-text-secondary)]">{t('flow.label')}</span>
        <FlowToggle flow={flow} switchingFlow={switchingFlow} availableFlows={availableFlows} onToggle={onFlowToggle} />
      </div>

      <div className="h-px bg-[var(--proto-border)]" />

      {/* Map display toggles */}
      <div className="flex flex-col gap-2">
        <span className="text-[length:var(--text-xs)] text-[var(--proto-text-secondary)]">Map</span>
        <label className="flex items-center justify-between cursor-pointer group">
          <span className="text-[length:var(--text-sm)] text-[var(--proto-text)]">3D Buildings</span>
          <button
            onClick={() => dispatch({ type: 'TOGGLE_3D_BUILDINGS' })}
            className={`relative w-8 h-[18px] rounded-full transition-colors ${show3DBuildings ? 'bg-[var(--proto-accent)]' : 'bg-[var(--proto-border)]'}`}
          >
            <span
              className={`absolute top-[2px] left-[2px] w-[14px] h-[14px] rounded-full bg-white transition-transform ${show3DBuildings ? 'translate-x-[14px]' : ''}`}
            />
          </button>
        </label>
        <label className="flex items-center justify-between cursor-pointer group">
          <span className="text-[length:var(--text-sm)] text-[var(--proto-text)]">Channel Helper</span>
          <button
            onClick={() => dispatch({ type: 'TOGGLE_CHANNEL_HELPER' })}
            className={`relative w-8 h-[18px] rounded-full transition-colors ${showChannelHelper ? 'bg-[var(--proto-accent)]' : 'bg-[var(--proto-border)]'}`}
          >
            <span
              className={`absolute top-[2px] left-[2px] w-[14px] h-[14px] rounded-full bg-white transition-transform ${showChannelHelper ? 'translate-x-[14px]' : ''}`}
            />
          </button>
        </label>
      </div>

      <div className="h-px bg-[var(--proto-border)]" />

      <div className="text-[length:var(--text-xs)] text-[var(--proto-text-secondary)]">
        Default speed thresholds per fiber. Sections inherit these unless overridden.
      </div>
      {cableGroups.map(([cableId, group]) => {
        const current = fiberThresholds[group.fibers[0].id] ?? defaultSpeedThresholds

        return (
          <div key={cableId} className="flex flex-col gap-2">
            <div className="flex items-center gap-2">
              <span className="text-[length:var(--text-sm)] font-medium text-[var(--proto-text)]">{group.name}</span>
            </div>
            {/* Per-direction color dots */}
            <div className="flex gap-4 pl-0.5">
              {group.fibers.map(f => (
                <FiberColorDot
                  key={f.id}
                  direction={f.direction}
                  color={getFiberColor(f, fiberColors)}
                  isPickerOpen={colorPickerOpen === f.id}
                  onTogglePicker={() => setColorPickerOpen(colorPickerOpen === f.id ? null : f.id)}
                  onSelect={c => dispatch({ type: 'SET_FIBER_COLOR', fiberId: f.id, color: c })}
                  onClosePicker={() => setColorPickerOpen(null)}
                  onMouseEnter={() => onHighlightFiber?.(f.id)}
                  onMouseLeave={() => onClearHighlight?.()}
                />
              ))}
            </div>
            <ThresholdEditor
              thresholds={current}
              onChange={t => {
                for (const f of group.fibers) {
                  dispatch({ type: 'SET_FIBER_THRESHOLDS', fiberId: f.id, thresholds: t })
                }
              }}
            />
          </div>
        )
      })}

      <div className="h-px bg-[var(--proto-border)]" />

      <LogoutButton />
    </div>
  )
}

function LogoutButton() {
  const { logout, username } = useAuth()
  const navigate = useNavigate()

  const handleLogout = async () => {
    await logout()
    navigate('/login')
  }

  return (
    <div className="flex flex-col gap-2">
      {username && (
        <span className="text-[length:var(--text-xs)] text-[var(--proto-text-muted)]">
          Signed in as <span className="text-[var(--proto-text-secondary)]">{username}</span>
        </span>
      )}
      <button
        onClick={handleLogout}
        className="w-full px-3 py-2 text-[length:var(--text-sm)] text-red-400 hover:text-red-300 hover:bg-red-500/10 rounded-md transition-colors cursor-pointer text-left"
      >
        Sign out
      </button>
    </div>
  )
}

function SectionDetail({
  section,
  onBack,
  liveStats,
  liveSeriesData,
  dispatch,
  fiberColors,
}: {
  section: Section
  onBack: () => void
  liveStats: Map<string, LiveSectionStats>
  liveSeriesData: Map<string, SectionDataPoint[]>
  dispatch: React.Dispatch<ProtoAction>
  fiberColors: Record<string, string>
}) {
  const fiber = findFiber(section.fiberId, section.direction)
  const fiberColor = fiber ? getFiberColor(fiber, fiberColors) : '#6366f1'

  const [timeRange, setTimeRange] = useState<TimeRange>('1m')

  // Chart data fetched at the resolution matching the selected time range
  const historySeries = useSectionHistory(section.id, timeRange)

  // KPIs use the always-on page-level stats (stable regardless of chart time range)
  const live = liveStats.get(section.id)
  const liveSeries = liveSeriesData.get(section.id)
  const displaySpeed = live?.avgSpeed != null ? Math.round(live.avgSpeed) : section.avgSpeed
  const displayFlow = live?.flow ?? section.flow
  const displayTravelTime = live?.travelTime ?? section.travelTime
  const displayOccupancy = live?.occupancy ?? section.occupancy

  // Sparklines from the page-level 1-minute data (not affected by chart time range)
  const SPARK_LENGTH = 30
  const speedSpark = liveSeries?.length ? liveSeries.slice(-SPARK_LENGTH).map(p => p.speed) : section.speedHistory
  const flowSpark = liveSeries?.length ? liveSeries.slice(-SPARK_LENGTH).map(p => p.flow) : section.countHistory
  const occupancySpark = liveSeries?.length ? liveSeries.slice(-SPARK_LENGTH).map(p => p.occupancy) : null

  // Compute trends from sparklines
  const speedTrend = computeTrend(speedSpark)
  const flowTrend = computeTrend(flowSpark)

  const kpis = [
    {
      label: 'Avg Speed',
      value: `${displaySpeed}`,
      unit: 'km/h',
      trend: speedSpark,
      color: '#6366f1',
      trendPct: speedTrend.pct,
      positiveIsGood: true,
    },
    {
      label: 'Flow',
      value: `${displayFlow}`,
      unit: 'veh/h',
      trend: flowSpark,
      color: '#8b5cf6',
      trendPct: flowTrend.pct,
      positiveIsGood: true,
    },
    { label: 'Occupancy', value: `${displayOccupancy}`, unit: '%', trend: occupancySpark, color: '#0ea5e9' },
    { label: 'Travel Time', value: `${displayTravelTime}`, unit: 'min', color: fiberColor },
  ]

  const chartData = historySeries.map(p => ({
    time: p.time,
    speed: p.speed,
    flow: p.flow,
    occupancy: p.occupancy,
  }))
  const tableData = historySeries.slice(-10).map(p => ({
    time: p.time,
    speed: p.speed,
    flow: p.flow,
    occupancy: p.occupancy,
  }))

  return (
    <div className="proto-analysis-enter flex flex-col">
      <div className="sticky top-0 z-10 bg-[var(--proto-surface)] border-b border-[var(--proto-border)] px-4 py-3 flex items-center gap-3">
        <button
          onClick={onBack}
          className="text-[var(--proto-text-muted)] hover:text-[var(--proto-text)] transition-colors text-[length:var(--text-sm)] cursor-pointer"
        >
          &larr; Back
        </button>
        <div className="min-w-0">
          <span className="text-[length:var(--text-sm)] font-semibold text-[var(--proto-text)] truncate block">
            {section.name}
          </span>
          {fiber && (
            <span className="text-[length:var(--text-2xs)] text-[var(--proto-text-muted)] flex items-center gap-1.5">
              <span
                className="inline-block w-2 h-2 rounded-full flex-shrink-0"
                style={{ backgroundColor: fiberColor }}
              />
              {fiber.name} · {fiber.direction === 0 ? 'Dir A' : 'Dir B'} · Ch {section.startChannel}–
              {section.endChannel}
            </span>
          )}
        </div>
      </div>

      <div className="px-4 py-4 flex flex-col gap-3">
        {/* KPI grid */}
        <div className="grid grid-cols-2 gap-3">
          {kpis.map(kpi => (
            <div key={kpi.label} className="rounded-lg border border-[var(--proto-border)] p-3">
              <div className="text-[length:var(--text-2xs)] text-[var(--proto-text-muted)] uppercase tracking-wider mb-1">
                {kpi.label}
                {kpi.trendPct !== undefined && (
                  <TrendBadge pct={kpi.trendPct} positiveIsGood={kpi.positiveIsGood ?? true} />
                )}
              </div>
              <div className="flex items-end justify-between">
                <div>
                  <span className="text-[length:var(--text-xl)] font-semibold text-[var(--proto-text)]">
                    {kpi.value}
                  </span>
                  <span className="text-[length:var(--text-xs)] text-[var(--proto-text-muted)] ml-1">{kpi.unit}</span>
                </div>
                {kpi.trend && <Sparkline data={kpi.trend} color={kpi.color} width={48} height={20} />}
              </div>
            </div>
          ))}
        </div>

        {/* Time series chart */}
        <div className="border-t border-[var(--proto-border)] pt-3">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-[length:var(--text-xs)] font-medium text-[var(--proto-text-muted)] uppercase tracking-wider">
              Time Series
            </h3>
            <div className="flex gap-1">
              {(['1m', '5m', '15m', '1h'] as TimeRange[]).map(r => (
                <button
                  key={r}
                  onClick={() => setTimeRange(r)}
                  className={cn(
                    'px-2 py-0.5 rounded text-[length:var(--text-2xs)] transition-colors cursor-pointer',
                    timeRange === r
                      ? 'bg-[var(--proto-accent)] text-white'
                      : 'bg-[var(--proto-surface)] text-[var(--proto-text-muted)] hover:text-[var(--proto-text)]',
                  )}
                >
                  {r}
                </button>
              ))}
            </div>
          </div>
          <TimeSeriesChart data={chartData} timeRange={timeRange} />
        </div>

        {/* Data table */}
        <div className="border-t border-[var(--proto-border)] pt-3">
          <h3 className="text-[length:var(--text-xs)] font-medium text-[var(--proto-text-muted)] uppercase tracking-wider mb-3">
            Recent Data
          </h3>
          <div className="overflow-x-auto">
            <table className="w-full text-[length:var(--text-xs)]">
              <thead>
                <tr className="text-[var(--proto-text-muted)] border-b border-[var(--proto-border)]">
                  <th className="text-left py-1.5 pr-3 font-medium">Time</th>
                  <th className="text-right py-1.5 px-3 font-medium">Speed</th>
                  <th className="text-right py-1.5 px-3 font-medium">Flow</th>
                  <th className="text-right py-1.5 pl-3 font-medium">Occ.</th>
                </tr>
              </thead>
              <tbody>
                {tableData.map((row, i) => (
                  <tr key={i} className="border-b border-[var(--proto-border)] text-[var(--proto-text-secondary)]">
                    <td className="py-1.5 pr-3">{row.time}</td>
                    <td className="text-right py-1.5 px-3">
                      <span style={{ color: getSpeedColor(row.speed, section.speedThresholds) }}>{row.speed}</span> km/h
                    </td>
                    <td className="text-right py-1.5 px-3">{row.flow} veh/h</td>
                    <td className="text-right py-1.5 pl-3">{row.occupancy}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Speed thresholds editor */}
        <ThresholdEditor
          thresholds={section.speedThresholds}
          onChange={t => dispatch({ type: 'UPDATE_SECTION_THRESHOLDS', id: section.id, thresholds: t })}
        />
      </div>
    </div>
  )
}

// ── Structure list ───────────────────────────────────────────────────

const structureTypeColors: Record<string, { bg: string; text: string; dot: string }> = {
  bridge: { bg: '#f59e0b', text: '#fbbf24', dot: '#f59e0b' },
  tunnel: { bg: '#6366f1', text: '#818cf8', dot: '#6366f1' },
}

const statusColors: Record<string, string> = {
  nominal: '#22c55e',
  warning: '#f59e0b',
  critical: '#ef4444',
}

function StructureList({
  structures,
  loading,
  allStatuses,
  search,
  dispatch,
  onHighlightSection,
  onClearHighlight,
}: {
  structures: Infrastructure[]
  loading: boolean
  allStatuses: Map<string, SHMStatus>
  search: string
  dispatch: React.Dispatch<ProtoAction>
  onHighlightSection?: (sectionId: string) => void
  onClearHighlight?: () => void
}) {
  if (loading) {
    return (
      <div className="flex items-center justify-center h-32 text-[var(--proto-text-muted)] text-[length:var(--text-sm)]">
        <span className="animate-pulse">Loading structures...</span>
      </div>
    )
  }

  if (structures.length === 0) {
    return (
      <div className="flex items-center justify-center h-32 text-[var(--proto-text-muted)] text-[length:var(--text-sm)]">
        No structures found
      </div>
    )
  }

  const q = search.toLowerCase()
  const filtered = q
    ? structures.filter(s => {
        const fiberName = findFiber(s.fiberId, s.direction ?? 0)?.name ?? s.fiberId
        return (
          s.name.toLowerCase().includes(q) || s.type.toLowerCase().includes(q) || fiberName.toLowerCase().includes(q)
        )
      })
    : structures

  return (
    <div className="flex flex-col px-3 py-1">
      {filtered.length === 0 ? (
        <div className="flex items-center justify-center h-24 text-[var(--proto-text-muted)] text-[length:var(--text-sm)]">
          No structures match "{search}"
        </div>
      ) : (
        filtered.map(structure => {
          const typeStyle = structureTypeColors[structure.type] ?? structureTypeColors.bridge
          const fiber = findFiber(structure.fiberId, structure.direction ?? 0)
          const status = allStatuses.get(structure.id)
          const dotColor = status ? (statusColors[status.status] ?? '#64748b') : '#64748b'

          return (
            <button
              key={structure.id}
              onClick={() => dispatch({ type: 'SELECT_STRUCTURE', id: structure.id })}
              onMouseEnter={() => onHighlightSection?.(structure.id)}
              onMouseLeave={() => onClearHighlight?.()}
              className="w-full text-left px-3 py-2 rounded-lg hover:bg-[var(--proto-surface-raised)] transition-colors cursor-pointer"
            >
              {/* Thumbnail or placeholder */}
              {structure.imageUrl ? (
                <img
                  src={structure.imageUrl}
                  alt={structure.name}
                  className="w-full h-24 rounded-md object-cover mb-2"
                />
              ) : (
                <div
                  className="w-full h-24 rounded-md mb-2 flex items-center justify-center"
                  style={{ backgroundColor: `${typeStyle.bg}20` }}
                >
                  {structure.type === 'bridge' ? (
                    <svg
                      width="28"
                      height="28"
                      viewBox="0 0 16 16"
                      fill="none"
                      stroke={typeStyle.text}
                      strokeWidth="1.5"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    >
                      <path d="M1 12h14" />
                      <path d="M3 12V7" />
                      <path d="M13 12V7" />
                      <path d="M3 7C3 7 5.5 4 8 4C10.5 4 13 7 13 7" />
                    </svg>
                  ) : (
                    <svg
                      width="28"
                      height="28"
                      viewBox="0 0 16 16"
                      fill="none"
                      stroke={typeStyle.text}
                      strokeWidth="1.5"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    >
                      <path d="M2 6c0-2 3-4 6-4s6 2 6 4" />
                      <path d="M2 6v6h12V6" />
                      <path d="M5 12V8" />
                      <path d="M11 12V8" />
                    </svg>
                  )}
                </div>
              )}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-1.5 min-w-0">
                  <span className="text-[length:var(--text-sm)] text-[var(--proto-text)] font-medium truncate">
                    {structure.name}
                  </span>
                  <span className="shrink-0 w-2 h-2 rounded-full" style={{ backgroundColor: dotColor }} />
                </div>
                <span className="text-[length:var(--text-xs)] text-[var(--proto-text-muted)] shrink-0">
                  {structure.type.charAt(0).toUpperCase() + structure.type.slice(1)} ·{' '}
                  {fiber?.name ?? structure.fiberId}
                </span>
              </div>
            </button>
          )
        })
      )}
    </div>
  )
}

// ── Structure detail ─────────────────────────────────────────────────

function StructureDetail({
  structure,
  shmStatus,
  spectralData,
  spectralLoading,
  peakData,
  peakLoading,
  dataSummary,
  onBack,
}: {
  structure: Infrastructure | null
  shmStatus: SHMStatus | null
  spectralData: SpectralTimeSeries | null
  spectralLoading: boolean
  peakData: PeakFrequencyData | null
  peakLoading: boolean
  dataSummary: SpectralSummary | null
  onBack: () => void
}) {
  const [comparisonStats, setComparisonStats] = useState<ComparisonStats | null>(null)
  const handleComparisonStats = useCallback((s: ComparisonStats | null) => setComparisonStats(s), [])

  if (!structure) {
    return (
      <div className="flex items-center justify-center h-32 text-[var(--proto-text-muted)] text-[length:var(--text-sm)]">
        Structure not found
      </div>
    )
  }

  const typeStyle = structureTypeColors[structure.type] ?? structureTypeColors.bridge
  const fiber = findFiber(structure.fiberId, structure.direction ?? 0)
  const statusColor = shmStatus ? (statusColors[shmStatus.status] ?? statusColors.nominal) : '#64748b'

  const kpis = [
    { label: 'Peak Freq', value: shmStatus ? `${shmStatus.currentMean.toFixed(1)}` : '--', unit: 'Hz' },
    { label: 'Baseline', value: shmStatus ? `${shmStatus.baselineMean.toFixed(1)}` : '--', unit: 'Hz' },
    { label: 'Deviation', value: shmStatus ? `${shmStatus.deviationSigma.toFixed(2)}` : '--', unit: 'σ' },
    { label: 'Status', value: shmStatus?.status ?? '--', unit: '', isStatus: true },
  ]

  return (
    <div className="proto-analysis-enter flex flex-col">
      {/* Header */}
      <div className="sticky top-0 z-10 bg-[var(--proto-surface)] border-b border-[var(--proto-border)] px-4 py-3 flex items-center gap-3">
        <button
          onClick={onBack}
          className="text-[var(--proto-text-muted)] hover:text-[var(--proto-text)] transition-colors text-[length:var(--text-sm)] cursor-pointer"
        >
          &larr; Back
        </button>
        <div className="min-w-0">
          <span className="text-[length:var(--text-sm)] font-semibold text-[var(--proto-text)] truncate block">
            {structure.name}
          </span>
          {fiber && (
            <span className="text-[length:var(--text-2xs)] text-[var(--proto-text-muted)] flex items-center gap-1.5">
              <span
                className="inline-block w-2 h-2 rounded-full flex-shrink-0"
                style={{ backgroundColor: typeStyle.dot }}
              />
              {structure.type} · {fiber.name} · Ch {structure.startChannel}–{structure.endChannel}
            </span>
          )}
        </div>
        {shmStatus && (
          <span
            className="text-[length:var(--text-2xs)] font-medium px-1.5 py-0.5 rounded capitalize shrink-0"
            style={{ backgroundColor: `${statusColor}20`, color: statusColor }}
          >
            {shmStatus.status}
          </span>
        )}
      </div>

      <div className="px-4 py-4 flex flex-col gap-3">
        {/* Image */}
        {structure.imageUrl && (
          <img
            src={structure.imageUrl}
            alt={structure.name}
            className="w-full max-h-32 object-cover rounded-lg border border-[var(--proto-border)]"
          />
        )}

        {/* KPI grid */}
        <div className="grid grid-cols-2 gap-3">
          {kpis.map(kpi => (
            <div key={kpi.label} className="rounded-lg border border-[var(--proto-border)] p-3">
              <div className="text-[length:var(--text-2xs)] text-[var(--proto-text-muted)] uppercase tracking-wider mb-1">
                {kpi.label}
              </div>
              <div className="flex items-end gap-1">
                {kpi.isStatus ? (
                  <span
                    className="text-[length:var(--text-sm)] font-semibold capitalize"
                    style={{ color: statusColor }}
                  >
                    {kpi.value}
                  </span>
                ) : (
                  <>
                    <span className="text-[length:var(--text-xl)] font-semibold text-[var(--proto-text)]">
                      {kpi.value}
                    </span>
                    <span className="text-[length:var(--text-xs)] text-[var(--proto-text-muted)]">{kpi.unit}</span>
                  </>
                )}
              </div>
            </div>
          ))}
        </div>

        {/* Frequency shift banner */}
        {comparisonStats &&
          (() => {
            const isNominal = shmStatus?.status === 'nominal'
            const shiftColor = isNominal
              ? 'text-[var(--proto-text)]'
              : comparisonStats.diff > 0
                ? 'text-green-400'
                : comparisonStats.diff < 0
                  ? 'text-red-400'
                  : 'text-[var(--proto-text)]'
            const pctColor = isNominal
              ? 'text-[var(--proto-text-muted)]'
              : comparisonStats.diff > 0
                ? 'text-green-500'
                : comparisonStats.diff < 0
                  ? 'text-red-500'
                  : 'text-[var(--proto-text-muted)]'
            return (
              <div className="flex items-center justify-between rounded-lg border border-[var(--proto-border)] bg-[var(--proto-surface-raised)] px-4 py-3">
                <div>
                  <span className={`text-[length:var(--text-xl)] font-bold ${shiftColor}`}>
                    {comparisonStats.diff > 0 ? '+' : ''}
                    {(comparisonStats.diff * 1000).toFixed(2)} mHz
                  </span>
                  <div className="flex items-center gap-2 mt-0.5">
                    <span className={`text-[length:var(--text-xs)] ${pctColor}`}>
                      ({comparisonStats.diffPercent > 0 ? '+' : ''}
                      {comparisonStats.diffPercent.toFixed(2)}%)
                    </span>
                    <span className="text-[length:var(--text-2xs)] text-[var(--proto-text-muted)]">
                      vs previous period
                    </span>
                  </div>
                </div>
                <div className="text-[length:var(--text-2xs)] text-[var(--proto-text-muted)] uppercase tracking-wider">
                  Freq Shift
                </div>
              </div>
            )
          })()}

        {/* Spectral Heatmap */}
        <div className="border-t border-[var(--proto-border)] pt-3">
          <h3 className="text-[length:var(--text-xs)] font-medium text-[var(--proto-text-muted)] uppercase tracking-wider mb-3">
            Spectral Heatmap
          </h3>
          <div className="rounded-lg bg-[var(--proto-surface-raised)] border border-[var(--proto-border)] p-2">
            {spectralLoading ? (
              <div className="h-[200px] rounded-lg bg-[var(--proto-surface-raised)] animate-pulse" />
            ) : spectralData ? (
              <SpectralHeatmapCanvas data={spectralData} />
            ) : (
              <div className="h-[200px] flex items-center justify-center text-[length:var(--text-xs)] text-[var(--proto-text-muted)]">
                No spectral data
              </div>
            )}
          </div>
        </div>

        {/* Peak Scatter */}
        <div className="border-t border-[var(--proto-border)] pt-3">
          <h3 className="text-[length:var(--text-xs)] font-medium text-[var(--proto-text-muted)] uppercase tracking-wider mb-3">
            Peak Frequencies
          </h3>
          <div className="rounded-lg bg-[var(--proto-surface-raised)] border border-[var(--proto-border)] p-2">
            {peakLoading ? (
              <div className="h-[170px] rounded-lg bg-[var(--proto-surface-raised)] animate-pulse" />
            ) : peakData ? (
              <PeakScatterPlot data={peakData} />
            ) : (
              <div className="h-[170px] flex items-center justify-center text-[length:var(--text-xs)] text-[var(--proto-text-muted)]">
                No peak data
              </div>
            )}
          </div>
        </div>

        {/* Comparison overlay */}
        <div className="border-t border-[var(--proto-border)] pt-3">
          <ComparisonSection dataSummary={dataSummary} onStats={handleComparisonStats} />
        </div>
      </div>
    </div>
  )
}

// ── Spectral heatmap (canvas) ────────────────────────────────────────

// Viridis colormap (256 colors, RGB)
const VIRIDIS: [number, number, number][] = [
  [68, 1, 84],
  [68, 2, 86],
  [69, 4, 87],
  [69, 5, 89],
  [70, 7, 90],
  [70, 8, 92],
  [70, 10, 93],
  [70, 11, 94],
  [71, 13, 96],
  [71, 14, 97],
  [71, 16, 99],
  [71, 17, 100],
  [71, 19, 101],
  [72, 20, 103],
  [72, 22, 104],
  [72, 23, 105],
  [72, 24, 106],
  [72, 26, 108],
  [72, 27, 109],
  [72, 28, 110],
  [72, 29, 111],
  [72, 31, 112],
  [72, 32, 113],
  [72, 33, 115],
  [72, 35, 116],
  [72, 36, 117],
  [72, 37, 118],
  [72, 38, 119],
  [72, 40, 120],
  [72, 41, 121],
  [71, 42, 122],
  [71, 44, 122],
  [71, 45, 123],
  [71, 46, 124],
  [71, 47, 125],
  [70, 48, 126],
  [70, 50, 126],
  [70, 51, 127],
  [69, 52, 128],
  [69, 53, 129],
  [69, 55, 129],
  [68, 56, 130],
  [68, 57, 131],
  [68, 58, 131],
  [67, 60, 132],
  [67, 61, 132],
  [66, 62, 133],
  [66, 63, 133],
  [66, 64, 134],
  [65, 66, 134],
  [65, 67, 135],
  [64, 68, 135],
  [64, 69, 136],
  [63, 71, 136],
  [63, 72, 137],
  [62, 73, 137],
  [62, 74, 137],
  [62, 76, 138],
  [61, 77, 138],
  [61, 78, 138],
  [60, 79, 139],
  [60, 80, 139],
  [59, 82, 139],
  [59, 83, 140],
  [58, 84, 140],
  [58, 85, 140],
  [57, 86, 141],
  [57, 88, 141],
  [56, 89, 141],
  [56, 90, 141],
  [55, 91, 142],
  [55, 92, 142],
  [54, 94, 142],
  [54, 95, 142],
  [53, 96, 142],
  [53, 97, 142],
  [52, 98, 143],
  [52, 100, 143],
  [51, 101, 143],
  [51, 102, 143],
  [50, 103, 143],
  [50, 105, 143],
  [49, 106, 143],
  [49, 107, 143],
  [49, 108, 143],
  [48, 109, 143],
  [48, 111, 143],
  [47, 112, 143],
  [47, 113, 143],
  [46, 114, 143],
  [46, 116, 143],
  [46, 117, 143],
  [45, 118, 143],
  [45, 119, 143],
  [44, 121, 142],
  [44, 122, 142],
  [44, 123, 142],
  [43, 124, 142],
  [43, 126, 142],
  [43, 127, 141],
  [42, 128, 141],
  [42, 129, 141],
  [42, 131, 140],
  [41, 132, 140],
  [41, 133, 140],
  [41, 135, 139],
  [40, 136, 139],
  [40, 137, 138],
  [40, 138, 138],
  [40, 140, 137],
  [39, 141, 137],
  [39, 142, 136],
  [39, 144, 136],
  [39, 145, 135],
  [39, 146, 134],
  [38, 148, 134],
  [38, 149, 133],
  [38, 150, 132],
  [38, 152, 131],
  [38, 153, 131],
  [38, 154, 130],
  [38, 156, 129],
  [38, 157, 128],
  [39, 158, 127],
  [39, 160, 126],
  [39, 161, 125],
  [39, 163, 124],
  [39, 164, 123],
  [40, 165, 122],
  [40, 167, 121],
  [40, 168, 120],
  [41, 169, 119],
  [41, 171, 118],
  [42, 172, 117],
  [42, 174, 116],
  [43, 175, 115],
  [43, 176, 113],
  [44, 178, 112],
  [45, 179, 111],
  [45, 181, 110],
  [46, 182, 108],
  [47, 183, 107],
  [48, 185, 106],
  [48, 186, 104],
  [49, 188, 103],
  [50, 189, 102],
  [51, 190, 100],
  [52, 192, 99],
  [53, 193, 97],
  [54, 195, 96],
  [55, 196, 94],
  [56, 197, 93],
  [58, 199, 91],
  [59, 200, 90],
  [60, 201, 88],
  [62, 203, 86],
  [63, 204, 85],
  [64, 206, 83],
  [66, 207, 81],
  [67, 208, 80],
  [69, 210, 78],
  [71, 211, 76],
  [72, 212, 74],
  [74, 214, 72],
  [76, 215, 71],
  [78, 216, 69],
  [79, 218, 67],
  [81, 219, 65],
  [83, 220, 63],
  [85, 221, 61],
  [87, 223, 59],
  [89, 224, 57],
  [91, 225, 55],
  [94, 226, 53],
  [96, 227, 51],
  [98, 229, 49],
  [100, 230, 47],
  [103, 231, 45],
  [105, 232, 43],
  [107, 233, 41],
  [110, 234, 39],
  [112, 235, 37],
  [115, 236, 35],
  [117, 237, 33],
  [120, 238, 31],
  [122, 239, 29],
  [125, 240, 27],
  [127, 241, 25],
  [130, 242, 24],
  [133, 243, 22],
  [135, 244, 21],
  [138, 245, 19],
  [141, 245, 18],
  [143, 246, 17],
  [146, 247, 16],
  [149, 248, 15],
  [151, 249, 14],
  [154, 249, 14],
  [157, 250, 14],
  [160, 251, 13],
  [162, 251, 13],
  [165, 252, 13],
  [168, 253, 14],
  [171, 253, 14],
  [173, 254, 15],
  [176, 254, 16],
  [179, 255, 17],
  [182, 255, 18],
  [185, 255, 19],
  [187, 255, 21],
  [190, 255, 22],
  [193, 255, 24],
  [196, 255, 25],
  [199, 255, 27],
  [201, 255, 29],
  [204, 255, 31],
  [207, 255, 33],
  [210, 255, 35],
  [212, 255, 38],
  [215, 255, 40],
  [218, 255, 42],
  [220, 255, 45],
  [223, 255, 47],
  [226, 255, 50],
  [228, 255, 53],
  [231, 255, 55],
  [233, 255, 58],
  [236, 255, 61],
  [238, 255, 64],
  [241, 255, 67],
  [243, 255, 70],
  [246, 255, 73],
  [248, 255, 76],
  [250, 255, 79],
  [253, 255, 82],
]

function SpectralHeatmapCanvas({ data }: { data: SpectralTimeSeries }) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const { width: debouncedWidth, transitioning } = useDebouncedResize(containerRef)

  const draw = useCallback(
    (width: number) => {
      const canvas = canvasRef.current
      if (!canvas || width <= 0) return

      const height = 200
      const dpr = window.devicePixelRatio || 1
      canvas.width = width * dpr
      canvas.height = height * dpr
      canvas.style.width = `${width}px`
      canvas.style.height = `${height}px`

      const ctx = canvas.getContext('2d')
      if (!ctx) return
      ctx.scale(dpr, dpr)

      const { spectra, freqs } = data
      if (!spectra.length || !freqs.length) return

      const margin = { top: 4, right: 8, bottom: 24, left: 56 }
      const plotW = width - margin.left - margin.right
      const plotH = height - margin.top - margin.bottom

      const numTime = spectra.length
      const numFreq = freqs.length

      // Find min/max power for color scaling
      let minP = Infinity,
        maxP = -Infinity
      for (const row of spectra) {
        for (const v of row) {
          if (v < minP) minP = v
          if (v > maxP) maxP = v
        }
      }
      const range = maxP - minP || 1

      // Draw heatmap
      const cellW = plotW / numTime
      const cellH = plotH / numFreq

      for (let ti = 0; ti < numTime; ti++) {
        for (let fi = 0; fi < numFreq; fi++) {
          const norm = (spectra[ti][fi] - minP) / range
          const idx = Math.floor(norm * (VIRIDIS.length - 1))
          const [r, g, b] = VIRIDIS[Math.max(0, Math.min(idx, VIRIDIS.length - 1))]
          ctx.fillStyle = `rgb(${r},${g},${b})`
          ctx.fillRect(
            margin.left + ti * cellW,
            margin.top + (numFreq - 1 - fi) * cellH,
            Math.ceil(cellW) + 1,
            Math.ceil(cellH) + 1,
          )
        }
      }

      // Axes
      ctx.fillStyle = '#64748b'
      ctx.font = '10px sans-serif'

      // X axis (time) — hour-aligned ticks like PeakScatterPlot
      ctx.textAlign = 'center'
      const t0 = new Date(data.t0)
      const tMin = t0.getTime()
      const tMax = tMin + (data.dt[data.dt.length - 1] || 0) * 1000
      const durH = (tMax - tMin) / (1000 * 3600)
      let interval = 1
      if (durH > 72) interval = 12
      else if (durH > 24) interval = 6
      else if (durH > 12) interval = 3
      else if (durH > 6) interval = 2
      const cur = new Date(tMin)
      cur.setMinutes(0, 0, 0)
      if (cur.getTime() < tMin) cur.setHours(cur.getHours() + 1)
      const aligned = Math.ceil(cur.getHours() / interval) * interval
      cur.setHours(aligned)
      while (cur.getTime() <= tMax) {
        if (cur.getTime() >= tMin) {
          const frac = (cur.getTime() - tMin) / (tMax - tMin || 1)
          const x = margin.left + frac * plotW
          const label = `${cur.getHours().toString().padStart(2, '0')}:00`
          ctx.fillText(label, x, height - 4)
        }
        cur.setHours(cur.getHours() + interval)
      }

      // Y axis (frequency) — integer Hz ticks
      ctx.textAlign = 'right'
      const freqLo = Math.ceil(freqs[0])
      const freqHi = Math.floor(freqs[freqs.length - 1])
      for (let hz = freqLo; hz <= freqHi; hz++) {
        const frac = (hz - freqs[0]) / (freqs[freqs.length - 1] - freqs[0])
        const y = margin.top + (1 - frac) * plotH + 3
        ctx.fillText(`${hz}`, margin.left - 4, y)
      }

      // Rotated vertical label: "Freq (Hz)"
      ctx.save()
      ctx.font = '9px sans-serif'
      ctx.textAlign = 'center'
      const labelX = 12
      const labelY = margin.top + plotH / 2
      ctx.translate(labelX, labelY)
      ctx.rotate(-Math.PI / 2)
      ctx.fillText('Freq (Hz)', 0, 0)
      ctx.restore()
    },
    [data],
  )

  useEffect(() => {
    draw(debouncedWidth)
  }, [draw, debouncedWidth])

  return (
    <div ref={containerRef} className="w-full" style={{ height: 200 }}>
      {transitioning ? (
        <div className="w-full h-full rounded-lg bg-[var(--proto-surface-raised)] animate-pulse" />
      ) : (
        <canvas ref={canvasRef} className="rounded" />
      )}
    </div>
  )
}

// ── Peak scatter plot (SHM-style dot cloud) ─────────────────────────

type ScatterTooltip = { x: number; y: number; freq: number; power: number; timestamp: Date } | null
type ScatterBrush = { startX: number; currentX: number } | null
type ScatterZoom = { startMs: number; endMs: number } | null

function formatScatterHour(date: Date): string {
  return `${date.getHours().toString().padStart(2, '0')}:00`
}

function PeakScatterPlot({ data }: { data: PeakFrequencyData }) {
  const containerRef = useRef<HTMLDivElement>(null)
  const svgRef = useRef<SVGSVGElement>(null)
  const { width, transitioning } = useDebouncedResize(containerRef)
  const [tooltip, setTooltip] = useState<ScatterTooltip>(null)
  const [brush, setBrush] = useState<ScatterBrush>(null)
  const [zoom, setZoom] = useState<ScatterZoom>(null)
  const rawId = useRef(Math.random().toString(36).slice(2)).current
  const clipId = `proto-scatter-${rawId}`

  const height = 170
  const padding = { top: 16, right: 12, bottom: 28, left: 48 }
  const plotW = width - padding.left - padding.right
  const plotH = height - padding.top - padding.bottom

  const t0 = useMemo(() => new Date(data.t0), [data.t0])

  const fullTimeRange = useMemo(() => {
    const min = t0.getTime()
    const max = min + (data.dt[data.dt.length - 1] || 0) * 1000
    return { min, max }
  }, [t0, data.dt])

  const timeRange = useMemo(() => {
    if (zoom) return { min: zoom.startMs, max: zoom.endMs }
    return fullTimeRange
  }, [zoom, fullTimeRange])

  const { points, xScale, yScale, freqMin, freqMax, inverseXScale } = useMemo(() => {
    const freqMin = 1.06
    const freqMax = 1.16

    let pMin = Infinity,
      pMax = -Infinity
    for (const p of data.peakPowers) {
      if (p < pMin) pMin = p
      if (p > pMax) pMax = p
    }
    const { min: timeMin, max: timeMax } = timeRange
    const xScale = (ms: number) => padding.left + ((ms - timeMin) / (timeMax - timeMin || 1)) * plotW
    const yScale = (f: number) => padding.top + ((freqMax - f) / (freqMax - freqMin || 1)) * plotH
    const inverseXScale = (px: number) => timeMin + ((px - padding.left) / plotW) * (timeMax - timeMin)

    const pts = data.dt.map((offsetSec, i) => {
      const ts = new Date(t0.getTime() + offsetSec * 1000)
      const ms = ts.getTime()
      const freq = data.peakFrequencies[i]
      return {
        x: xScale(ms),
        y: yScale(freq),
        freq,
        power: data.peakPowers[i],
        timestamp: ts,
        size: 2 + ((data.peakPowers[i] - pMin) / (pMax - pMin + 1e-10)) * 4,
        inRange: freq >= freqMin && freq <= freqMax,
        inTimeRange: ms >= timeMin && ms <= timeMax,
      }
    })
    return { points: pts, xScale, yScale, freqMin, freqMax, inverseXScale }
  }, [data, t0, plotW, plotH, padding.left, padding.top, timeRange])

  const yTicks = useMemo(() => {
    const count = 5
    const step = (freqMax - freqMin) / (count - 1)
    return Array.from({ length: count }, (_, i) => freqMin + i * step)
  }, [freqMin, freqMax])

  const xTicks = useMemo(() => {
    const ticks: { x: number; label: string }[] = []
    const { min: tMin, max: tMax } = timeRange
    const durH = (tMax - tMin) / (1000 * 3600)
    let interval = 1
    if (durH > 72) interval = 12
    else if (durH > 24) interval = 6
    else if (durH > 12) interval = 3
    else if (durH > 6) interval = 2
    const cur = new Date(tMin)
    cur.setMinutes(0, 0, 0)
    if (cur.getTime() < tMin) cur.setHours(cur.getHours() + 1)
    const aligned = Math.ceil(cur.getHours() / interval) * interval
    cur.setHours(aligned)
    while (cur.getTime() <= tMax) {
      if (cur.getTime() >= tMin) ticks.push({ x: xScale(cur.getTime()), label: formatScatterHour(cur) })
      cur.setHours(cur.getHours() + interval)
    }
    return ticks
  }, [timeRange, xScale])

  // Brush handlers
  const getMouseX = useCallback((e: React.MouseEvent) => {
    if (!svgRef.current) return 0
    return e.clientX - svgRef.current.getBoundingClientRect().left
  }, [])

  const handleMouseDown = useCallback(
    (e: React.MouseEvent) => {
      const x = getMouseX(e)
      if (x >= padding.left && x <= width - padding.right) {
        setBrush({ startX: x, currentX: x })
        setTooltip(null)
      }
    },
    [getMouseX, padding.left, width, padding.right],
  )

  const handleMouseMove = useCallback(
    (e: React.MouseEvent) => {
      if (brush) {
        const x = Math.max(padding.left, Math.min(width - padding.right, getMouseX(e)))
        setBrush(prev => (prev ? { ...prev, currentX: x } : null))
      }
    },
    [brush, getMouseX, padding.left, width, padding.right],
  )

  const handleMouseUp = useCallback(() => {
    if (brush) {
      const minX = Math.min(brush.startX, brush.currentX)
      const maxX = Math.max(brush.startX, brush.currentX)
      if (maxX - minX > 10) setZoom({ startMs: inverseXScale(minX), endMs: inverseXScale(maxX) })
      setBrush(null)
    }
  }, [brush, inverseXScale])

  const brushRect = brush
    ? { x: Math.min(brush.startX, brush.currentX), width: Math.abs(brush.currentX - brush.startX) }
    : null

  if (!data.dt.length) return <div className="h-[170px]" ref={containerRef} />

  if (transitioning) {
    return (
      <div ref={containerRef} className="relative h-[170px]">
        <div className="w-full h-full rounded-lg bg-[var(--proto-surface-raised)] animate-pulse" />
      </div>
    )
  }

  return (
    <div ref={containerRef} className="w-full relative">
      {zoom && (
        <button
          onClick={() => setZoom(null)}
          className="absolute top-0 right-0 z-10 flex items-center gap-1 px-2 py-1 text-[length:var(--text-2xs)] text-[var(--proto-text-muted)] hover:text-[var(--proto-text)] rounded transition-colors cursor-pointer"
        >
          ↺ Reset
        </button>
      )}
      <div className="overflow-hidden">
        <svg
          ref={svgRef}
          width="100%"
          height={height}
          viewBox={`0 0 ${width} ${height}`}
          preserveAspectRatio="xMidYMid meet"
          className="select-none"
          onMouseDown={handleMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          onMouseLeave={() => {
            if (brush) setBrush(null)
          }}
          onDoubleClick={() => setZoom(null)}
        >
          <defs>
            <clipPath id={clipId}>
              <rect x={padding.left} y={padding.top} width={plotW} height={plotH} />
            </clipPath>
          </defs>

          {/* Y-axis */}
          <line
            x1={padding.left}
            y1={padding.top}
            x2={padding.left}
            y2={height - padding.bottom}
            stroke="rgba(255,255,255,0.08)"
            strokeWidth={1}
          />
          {yTicks.map(tick => (
            <g key={tick}>
              <line
                x1={padding.left - 3}
                y1={yScale(tick)}
                x2={padding.left}
                y2={yScale(tick)}
                stroke="#64748b"
                strokeWidth={1}
              />
              <text
                x={padding.left - 6}
                y={yScale(tick)}
                textAnchor="end"
                dominantBaseline="middle"
                fill="#64748b"
                fontSize="10"
              >
                {tick.toFixed(2)}
              </text>
            </g>
          ))}
          <text
            x={4}
            y={height / 2}
            textAnchor="middle"
            dominantBaseline="middle"
            transform={`rotate(-90, 4, ${height / 2})`}
            fill="#64748b"
            fontSize="9"
          >
            Peak Freq (Hz)
          </text>

          {/* X-axis */}
          <line
            x1={padding.left}
            y1={height - padding.bottom}
            x2={width - padding.right}
            y2={height - padding.bottom}
            stroke="rgba(255,255,255,0.08)"
            strokeWidth={1}
          />
          {xTicks.map((tick, i) => (
            <g key={i}>
              <line
                x1={tick.x}
                y1={height - padding.bottom}
                x2={tick.x}
                y2={height - padding.bottom + 3}
                stroke="#64748b"
                strokeWidth={1}
              />
              <text x={tick.x} y={height - padding.bottom + 14} textAnchor="middle" fill="#64748b" fontSize="10">
                {tick.label}
              </text>
            </g>
          ))}

          {/* Grid lines */}
          {yTicks.map(tick => (
            <line
              key={`g-${tick}`}
              x1={padding.left + 1}
              y1={yScale(tick)}
              x2={width - padding.right}
              y2={yScale(tick)}
              stroke="rgba(255,255,255,0.03)"
              strokeWidth={1}
            />
          ))}

          {/* Data points */}
          <g clipPath={`url(#${clipId})`}>
            {points
              .filter(pt => pt.inRange && pt.inTimeRange)
              .map((pt, i) => (
                <circle
                  key={i}
                  cx={pt.x}
                  cy={pt.y}
                  r={pt.size}
                  fill="#f59e0b"
                  fillOpacity={0.12}
                  stroke="none"
                  className="cursor-crosshair hover:!fill-opacity-60"
                  onMouseEnter={e => {
                    e.stopPropagation()
                    if (!brush)
                      setTooltip({ x: pt.x, y: pt.y, freq: pt.freq, power: pt.power, timestamp: pt.timestamp })
                  }}
                  onMouseLeave={() => setTooltip(null)}
                />
              ))}
          </g>

          {/* Brush */}
          {brushRect && (
            <rect
              x={brushRect.x}
              y={padding.top}
              width={brushRect.width}
              height={plotH}
              fill="var(--proto-accent)"
              fillOpacity={0.15}
              stroke="var(--proto-accent)"
              strokeWidth={1}
              pointerEvents="none"
            />
          )}
        </svg>
      </div>

      {/* Tooltip */}
      {tooltip && !brush && (
        <div
          className="absolute bg-[var(--proto-surface-raised)] text-[var(--proto-text)] text-[length:var(--text-2xs)] px-2 py-1.5 rounded shadow-lg pointer-events-none z-10 whitespace-nowrap border border-[var(--proto-border)]"
          style={{
            left: tooltip.x > width * 0.6 ? undefined : tooltip.x + 10,
            right: tooltip.x > width * 0.6 ? width - tooltip.x + 10 : undefined,
            top: tooltip.y - 10,
            transform: 'translateY(-100%)',
          }}
        >
          <div>Freq: {tooltip.freq.toFixed(3)} Hz</div>
          <div>Power: {tooltip.power.toFixed(2)}</div>
          <div className="text-[var(--proto-text-muted)]">
            {tooltip.timestamp.toLocaleString(undefined, {
              month: 'short',
              day: 'numeric',
              hour: '2-digit',
              minute: '2-digit',
            })}
          </div>
        </div>
      )}
    </div>
  )
}

// ── Comparison overlay scatter ───────────────────────────────────────

type ComparisonMode = 'day' | 'week'
type FocusMode = 'A' | 'equal' | 'B'

function ComparisonOverlay({
  dataA,
  dataB,
  focus,
  width,
}: {
  dataA: PeakFrequencyData | null
  dataB: PeakFrequencyData | null
  focus: FocusMode
  width: number
}) {
  const rawId = useRef(Math.random().toString(36).slice(2)).current
  const clipId = `proto-overlay-${rawId}`
  const height = 140
  const padding = { top: 12, right: 12, bottom: 22, left: 48 }
  const plotW = Math.max(80, width - padding.left - padding.right)
  const plotH = height - padding.top - padding.bottom

  const freqMin = 1.06,
    freqMax = 1.16
  const yScale = (f: number) => padding.top + ((freqMax - f) / (freqMax - freqMin)) * plotH

  const processData = (data: PeakFrequencyData | null, color: string) => {
    if (!data || !data.dt.length) return []
    const duration = (data.dt[data.dt.length - 1] || 1) * 1000
    return data.dt.map((off, i) => {
      const nx = (off * 1000) / duration
      const freq = data.peakFrequencies[i]
      return { x: padding.left + nx * plotW, y: yScale(freq), freq, inRange: freq >= freqMin && freq <= freqMax, color }
    })
  }

  const pointsA = processData(dataA, '#3b82f6')
  const pointsB = processData(dataB, '#f59e0b')
  const opacityA = focus === 'A' ? 0.7 : focus === 'equal' ? 0.3 : 0.04
  const opacityB = focus === 'B' ? 0.7 : focus === 'equal' ? 0.3 : 0.04
  const yTicks = [1.06, 1.09, 1.12, 1.16]

  return (
    <svg
      width="100%"
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className="overflow-visible"
      preserveAspectRatio="xMidYMid meet"
    >
      <defs>
        <clipPath id={clipId}>
          <rect x={padding.left} y={padding.top} width={plotW} height={plotH} />
        </clipPath>
      </defs>

      {/* Y-axis */}
      <line
        x1={padding.left}
        y1={padding.top}
        x2={padding.left}
        y2={height - padding.bottom}
        stroke="rgba(255,255,255,0.08)"
        strokeWidth={1}
      />
      {yTicks.map(tick => (
        <g key={tick}>
          <line
            x1={padding.left - 3}
            y1={yScale(tick)}
            x2={padding.left}
            y2={yScale(tick)}
            stroke="#64748b"
            strokeWidth={1}
          />
          <text
            x={padding.left - 6}
            y={yScale(tick)}
            textAnchor="end"
            dominantBaseline="middle"
            fill="#64748b"
            fontSize="10"
          >
            {tick.toFixed(2)}
          </text>
          <line
            x1={padding.left + 1}
            y1={yScale(tick)}
            x2={width - padding.right}
            y2={yScale(tick)}
            stroke="rgba(255,255,255,0.03)"
            strokeWidth={1}
          />
        </g>
      ))}
      <text
        x={4}
        y={height / 2}
        textAnchor="middle"
        dominantBaseline="middle"
        transform={`rotate(-90, 4, ${height / 2})`}
        fill="#64748b"
        fontSize="9"
      >
        Freq (Hz)
      </text>

      {/* X-axis */}
      <line
        x1={padding.left}
        y1={height - padding.bottom}
        x2={width - padding.right}
        y2={height - padding.bottom}
        stroke="rgba(255,255,255,0.08)"
        strokeWidth={1}
      />
      <text x={padding.left} y={height - 4} textAnchor="start" fill="#4a5568" fontSize="9">
        start
      </text>
      <text x={width - padding.right} y={height - 4} textAnchor="end" fill="#4a5568" fontSize="9">
        end
      </text>

      {/* Dots: render unfocused behind, focused in front */}
      <g clipPath={`url(#${clipId})`}>
        {focus !== 'A' &&
          pointsB
            .filter(p => p.inRange)
            .map((pt, i) => (
              <circle key={`b-${i}`} cx={pt.x} cy={pt.y} r={2.5} fill={pt.color} fillOpacity={opacityB} />
            ))}
        {pointsA
          .filter(p => p.inRange)
          .map((pt, i) => (
            <circle key={`a-${i}`} cx={pt.x} cy={pt.y} r={2.5} fill={pt.color} fillOpacity={opacityA} />
          ))}
        {focus === 'A' &&
          pointsB
            .filter(p => p.inRange)
            .map((pt, i) => (
              <circle key={`b2-${i}`} cx={pt.x} cy={pt.y} r={2.5} fill={pt.color} fillOpacity={opacityB} />
            ))}
      </g>
    </svg>
  )
}

type ComparisonStats = {
  a: { mean: number; std: number; count: number }
  b: { mean: number; std: number; count: number }
  diff: number
  diffPercent: number
}

function ComparisonSection({
  dataSummary,
  onStats,
}: {
  dataSummary: SpectralSummary | null
  onStats?: (stats: ComparisonStats | null) => void
}) {
  const containerRef = useRef<HTMLDivElement>(null)
  const { width: rawChartWidth, transitioning: chartTransitioning } = useDebouncedResize(containerRef)
  const chartWidth = Math.max(160, rawChartWidth)
  const [mode, setMode] = useState<ComparisonMode>('day')
  const [focus, setFocus] = useState<FocusMode>('equal')
  const [windowA, setWindowA] = useState<{ data: PeakFrequencyData | null; loading: boolean }>({
    data: null,
    loading: false,
  })
  const [windowB, setWindowB] = useState<{ data: PeakFrequencyData | null; loading: boolean }>({
    data: null,
    loading: false,
  })

  // Compute comparison date ranges
  const referenceDate = useMemo(() => {
    return dataSummary?.endTime ? new Date(dataSummary.endTime) : new Date()
  }, [dataSummary?.endTime])

  const { rangeA, rangeB, labelA, labelB } = useMemo(() => {
    const latestDay = new Date(referenceDate)
    latestDay.setHours(0, 0, 0, 0)

    if (mode === 'day') {
      const prevDay = new Date(latestDay)
      prevDay.setDate(prevDay.getDate() - 1)
      const endA = new Date(latestDay)
      endA.setHours(23, 59, 59, 999)
      const endB = new Date(prevDay)
      endB.setHours(23, 59, 59, 999)
      return {
        rangeA: { from: latestDay, to: endA },
        rangeB: { from: prevDay, to: endB },
        labelA: latestDay.toLocaleDateString(undefined, { month: 'short', day: 'numeric' }),
        labelB: prevDay.toLocaleDateString(undefined, { month: 'short', day: 'numeric' }),
      }
    }
    // week mode
    const dayOfWeek = latestDay.getDay()
    const mondayOffset = dayOfWeek === 0 ? -6 : 1 - dayOfWeek
    const thisMonday = new Date(latestDay)
    thisMonday.setDate(thisMonday.getDate() + mondayOffset)
    const thisSunday = new Date(thisMonday)
    thisSunday.setDate(thisSunday.getDate() + 6)
    thisSunday.setHours(23, 59, 59, 999)
    const lastMonday = new Date(thisMonday)
    lastMonday.setDate(lastMonday.getDate() - 7)
    const lastSunday = new Date(lastMonday)
    lastSunday.setDate(lastSunday.getDate() + 6)
    lastSunday.setHours(23, 59, 59, 999)
    const fmt = (d: Date) => d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
    return {
      rangeA: { from: thisMonday, to: thisSunday },
      rangeB: { from: lastMonday, to: lastSunday },
      labelA: `${fmt(thisMonday)} – ${fmt(thisSunday)}`,
      labelB: `${fmt(lastMonday)} – ${fmt(lastSunday)}`,
    }
  }, [mode, referenceDate])

  // Fetch comparison data
  const rangeAFromMs = rangeA.from.getTime()
  const rangeAToMs = rangeA.to.getTime()
  const rangeBFromMs = rangeB.from.getTime()
  const rangeBToMs = rangeB.to.getTime()

  useEffect(() => {
    let cancelled = false
    setWindowA({ data: null, loading: true })
    fetchPeakFrequencies({ maxSamples: 5000, startTime: rangeA.from, endTime: rangeA.to })
      .then(data => {
        if (!cancelled) setWindowA({ data, loading: false })
      })
      .catch(() => {
        if (!cancelled) setWindowA({ data: null, loading: false })
      })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- rangeA.from/to are Date objects; use ms timestamps for stable comparison
  }, [rangeAFromMs, rangeAToMs])

  useEffect(() => {
    let cancelled = false
    setWindowB({ data: null, loading: true })
    fetchPeakFrequencies({ maxSamples: 5000, startTime: rangeB.from, endTime: rangeB.to })
      .then(data => {
        if (!cancelled) setWindowB({ data, loading: false })
      })
      .catch(() => {
        if (!cancelled) setWindowB({ data: null, loading: false })
      })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- rangeB.from/to are Date objects; use ms timestamps for stable comparison
  }, [rangeBFromMs, rangeBToMs])

  // Stats
  const stats = useMemo(() => {
    const calc = (d: PeakFrequencyData | null) => {
      if (!d) return null
      const valid = d.peakFrequencies.filter(f => f >= 1.05 && f <= 1.2)
      if (!valid.length) return null
      const mean = valid.reduce((a, b) => a + b, 0) / valid.length
      const variance = valid.reduce((s, f) => s + (f - mean) ** 2, 0) / valid.length
      return { mean, std: Math.sqrt(variance), count: valid.length }
    }
    const a = calc(windowA.data),
      b = calc(windowB.data)
    if (!a || !b) return null
    const diff = a.mean - b.mean
    return { a, b, diff, diffPercent: (diff / b.mean) * 100 }
  }, [windowA.data, windowB.data])

  const isLoading = windowA.loading || windowB.loading

  // Expose stats to parent
  useEffect(() => {
    onStats?.(stats)
  }, [stats, onStats])

  return (
    <div>
      {/* Header row */}
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-[length:var(--text-xs)] font-medium text-[var(--proto-text-muted)] uppercase tracking-wider">
          Comparison
        </h3>
        <div className="flex items-center gap-2">
          {/* Mode selector */}
          <select
            value={mode}
            onChange={e => setMode(e.target.value as ComparisonMode)}
            className="text-[length:var(--text-2xs)] bg-[var(--proto-surface-raised)] text-[var(--proto-text-secondary)] border border-[var(--proto-border)] rounded px-1.5 py-0.5 cursor-pointer"
          >
            <option value="day">Day / Day</option>
            <option value="week">Week / Week</option>
          </select>
          {/* Focus toggle */}
          <div className="flex items-center bg-[var(--proto-surface-raised)] rounded p-0.5 border border-[var(--proto-border)]">
            {(['A', 'equal', 'B'] as FocusMode[]).map(f => (
              <button
                key={f}
                onClick={() => setFocus(f)}
                className={cn(
                  'px-2 py-0.5 text-[length:var(--text-2xs)] font-medium rounded transition-colors cursor-pointer',
                  focus === f
                    ? f === 'A'
                      ? 'bg-blue-500 text-white'
                      : f === 'B'
                        ? 'bg-amber-500 text-white'
                        : 'bg-[var(--proto-text-muted)] text-white'
                    : 'text-[var(--proto-text-muted)] hover:text-[var(--proto-text)]',
                )}
              >
                {f === 'equal' ? '=' : f}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Period labels */}
      <div className="flex items-center gap-3 mb-2 text-[length:var(--text-2xs)]">
        <div className="flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-full bg-blue-500 shrink-0" />
          <span className="text-[var(--proto-text-secondary)]">A: {labelA}</span>
        </div>
        <span className="text-[var(--proto-text-muted)]">vs</span>
        <div className="flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-full bg-amber-500 shrink-0" />
          <span className="text-[var(--proto-text-secondary)]">B: {labelB}</span>
        </div>
      </div>

      {/* Chart */}
      <div
        ref={containerRef}
        className="rounded-lg bg-[var(--proto-surface-raised)] border border-[var(--proto-border)] p-2"
      >
        {isLoading || chartTransitioning ? (
          <div className="flex items-center justify-center h-[140px]">
            {isLoading ? (
              <div className="w-4 h-4 border-2 border-[var(--proto-text-muted)] border-t-transparent rounded-full animate-spin" />
            ) : (
              <div className="w-full h-full rounded-lg bg-[var(--proto-surface-raised)] animate-pulse" />
            )}
          </div>
        ) : (
          <ComparisonOverlay dataA={windowA.data} dataB={windowB.data} focus={focus} width={chartWidth} />
        )}
      </div>

      {/* Stats (A/B mean and σ only — shift banner is in StructureDetail) */}
      {stats && (
        <div className="mt-2">
          <div className="grid grid-cols-2 gap-2 text-[length:var(--text-2xs)]">
            <div className="flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-blue-500" />
              <span className="text-[var(--proto-text-muted)]">μ</span>
              <span className="text-[var(--proto-text-secondary)]">{stats.a.mean.toFixed(4)} Hz</span>
              <span className="text-[var(--proto-text-muted)]">(σ={stats.a.std.toFixed(4)})</span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-amber-500" />
              <span className="text-[var(--proto-text-muted)]">μ</span>
              <span className="text-[var(--proto-text-secondary)]">{stats.b.mean.toFixed(4)} Hz</span>
              <span className="text-[var(--proto-text-muted)]">(σ={stats.b.std.toFixed(4)})</span>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
