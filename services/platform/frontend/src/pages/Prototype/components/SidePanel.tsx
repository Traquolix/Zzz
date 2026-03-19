import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import i18next from 'i18next'
import { useAuth } from '@/hooks/useAuth'
import { cn } from '@/lib/utils'
import { severityColor, chartColors } from '../data'
import type { ProtoState, ProtoAction, Severity, MetricKey, LiveSectionStats, SectionDataPoint } from '../types'
import type {
  Infrastructure,
  SHMStatus,
  SpectralTimeSeries,
  PeakFrequencyData,
  SpectralSummary,
} from '@/types/infrastructure'
import { MAX_SECTIONS_PER_ORG } from '@/api/sections'
import { toast } from 'sonner'
import { API_URL } from '@/constants/api'
import { useRealtime } from '@/hooks/useRealtime'
import { ErrorBoundary } from '@/components/ui/ErrorBoundary'
import { WaterfallPanel } from './WaterfallPanel'
import { DataHubPanel, type DataHubSubTab } from './DataHubPanel'
import { ChannelDetail } from './ChannelDetail'
import { SectionList, SectionDetail } from './SectionPanels'
import { SettingsPanel } from './SettingsPanel'
import { StructureList, StructureDetail } from './StructurePanels'
import { IncidentList, IncidentDetail } from './IncidentPanels'
import {
  TabButton,
  SidebarIcon,
  IncidentsIcon,
  SectionsIcon,
  MetricIcon,
  ExpandIcon,
  SettingsIcon,
  BridgeIcon,
  ChannelIcon,
  DataHubIcon,
} from './SidebarIcons'

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
  panelRef: React.RefObject<HTMLDivElement | null>
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
  onMarkAllSeen?: () => void
}

const severityOrder: Severity[] = ['critical', 'high', 'medium', 'low']

/** Compact fallback UI for panel-level error boundaries. */
const panelFallback = (retry: () => void) => (
  <div className="flex flex-col items-center justify-center gap-3 py-12 px-4 text-center">
    <svg
      width="28"
      height="28"
      viewBox="0 0 24 24"
      fill="none"
      stroke="var(--proto-text-muted)"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
    </svg>
    <span className="text-[length:var(--text-sm)] text-[var(--proto-text-muted)]">
      {i18next.t('common.somethingWentWrong')}
    </span>
    <button
      onClick={retry}
      className="px-3 py-1.5 rounded text-[length:var(--text-xs)] font-medium text-[var(--proto-text-secondary)] bg-[var(--proto-surface-raised)] hover:text-[var(--proto-text)] transition-colors cursor-pointer"
    >
      {i18next.t('common.tryAgain')}
    </button>
  </div>
)

export function SidePanel({
  state,
  dispatch,
  panelRef,
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
  onMarkAllSeen,
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
  const { t } = useTranslation()
  const { isSuperuser, role } = useAuth()
  const isAdmin = isSuperuser || role === 'admin'
  const [incidentSortBy, setIncidentSortBy] = useState<'newest' | 'oldest'>('newest')
  const [shmSearch, setShmSearch] = useState('')
  const [sectionSearch, setSectionSearch] = useState('')
  const [dataHubSubTab, setDataHubSubTab] = useState<DataHubSubTab>('export')
  const [showCreateKey, setShowCreateKey] = useState(false)

  const incident = selectedIncidentId ? incidents.find(i => i.id === selectedIncidentId) : null
  const section = selectedSectionId ? sections.find(s => s.id === selectedSectionId) : null

  // Track when the slide transition finishes so we can delay showing/hiding elements
  const [fullyClosed, setFullyClosed] = useState(!sidebarOpen)

  useEffect(() => {
    if (sidebarOpen) {
      setFullyClosed(false)
    }
  }, [sidebarOpen])

  const handleTransitionEnd = (e: React.TransitionEvent) => {
    // Only act on the transform transition (the slide), not width or other properties
    if (e.propertyName !== 'transform') return
    if (!sidebarOpen) {
      setFullyClosed(true)
      if (sidebarExpanded) dispatch({ type: 'RESET_SIDEBAR_EXPANDED' })
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
            transition: sidebarOpen
              ? 'opacity 150ms 80ms ease-in'
              : `opacity ${sidebarExpanded ? '200ms' : '100ms'} ease-out`,
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
            <button
              title={sidebarExpanded ? t('sidebar.collapsePanel') : t('sidebar.expandPanel')}
              onClick={() => dispatch({ type: 'TOGGLE_SIDEBAR_EXPANDED' })}
              className="group/exp flex items-center justify-center self-end w-[32px] hover:w-full h-7 rounded-l-lg border border-r-0 border-transparent bg-[var(--proto-surface)]/40 text-[var(--proto-text-muted)] hover:text-[var(--proto-text-secondary)] hover:bg-[var(--proto-surface)]/80 transition-all cursor-pointer"
            >
              <ExpandIcon expanded={!!sidebarExpanded} />
            </button>
            {selectedChannel && (
              <TabButton
                label="Channel"
                icon={<ChannelIcon />}
                active={activeTab === 'channel'}
                onClick={() => dispatch({ type: 'SELECT_CHANNEL', channel: selectedChannel })}
              />
            )}
            {activeTab === 'settings' && (
              <TabButton
                label="Settings"
                icon={<SettingsIcon />}
                active
                onClick={() => dispatch({ type: 'SET_TAB', tab: 'settings' })}
              />
            )}
            {activeTab === 'dataHub' && (
              <TabButton
                label="Data Hub"
                icon={<DataHubIcon />}
                active
                onClick={() => dispatch({ type: 'SET_TAB', tab: 'dataHub' })}
              />
            )}
          </div>
        </div>

        {/* Panel header */}
        <div className="flex items-center justify-between px-4 h-[52px] shrink-0 border-b border-[var(--proto-border)]">
          <div className="flex items-center gap-3">
            <span className="text-[length:var(--text-sm)] font-medium text-[var(--proto-text-muted)] uppercase tracking-wider">
              {activeTab === 'dataHub'
                ? t('userMenu.dataHub')
                : activeTab === 'shm'
                  ? t('admin.widgetNames.shm')
                  : activeTab}
            </span>
            {activeTab === 'dataHub' && isAdmin && (
              <div className="flex items-center gap-0.5">
                {(['export', 'apiKeys'] as const).map(tab => (
                  <button
                    key={tab}
                    onClick={() => {
                      setDataHubSubTab(tab)
                      if (tab !== 'apiKeys') setShowCreateKey(false)
                    }}
                    className={`relative px-2 py-1 text-[length:var(--text-xxs)] font-medium transition-colors cursor-pointer rounded ${
                      dataHubSubTab === tab
                        ? 'text-[var(--proto-text)] bg-[var(--proto-surface-raised)]'
                        : 'text-[var(--proto-text-muted)] hover:text-[var(--proto-text-secondary)]'
                    }`}
                  >
                    {t(tab === 'export' ? 'export.sectionTitle' : 'apiKeys.sectionTitle')}
                  </button>
                ))}
              </div>
            )}
          </div>
          <div className="flex items-center gap-2">
            {activeTab === 'incidents' && (
              <>
                {filterSeverity && (
                  <button
                    onClick={() => dispatch({ type: 'SET_FILTER_SEVERITY', severity: null })}
<<<<<<< fix/80-i18n-sweep
                    className="w-3 h-3 rounded-full transition-all cursor-pointer opacity-50 hover:opacity-80"
                    style={{ backgroundColor: 'var(--proto-text-muted)' }}
                    title={t('incidents.filters.clearFilter')}
=======
                    className="w-3 h-3 rounded-full transition-all cursor-pointer opacity-50 hover:opacity-80 bg-[var(--proto-text-muted)]"
                    title="Clear filter"
>>>>>>> main
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
                    title={t(`incidents.severity.${s}`)}
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
                  title={hideResolved ? t('incidents.filters.showResolved') : t('incidents.filters.hideResolved')}
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
                  title={showIncidentsOnMap ? t('sidebar.hideOnMap') : t('sidebar.showOnMap')}
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
                  title={incidentSortBy === 'newest' ? t('sidebar.newestFirst') : t('sidebar.oldestFirst')}
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
                {hasUnseen && (
                  <button
                    onClick={onMarkAllSeen}
                    className="flex items-center justify-center w-6 h-6 rounded text-[var(--proto-text-muted)] hover:text-[var(--proto-text)] transition-colors cursor-pointer"
                    title={t('notifications.markAllRead')}
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
                      <path d="M18 6L7 17l-5-5" />
                      <path d="M22 10l-7.5 7.5L13 16" />
                    </svg>
                  </button>
                )}
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
                    placeholder={t('common.search')}
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
                  title={t('sidebar.showOnMap')}
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
                  title={t('sidebar.showLabels')}
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
                    placeholder={t('common.search')}
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
                      ? t('sidebar.sectionLimitReached', { max: MAX_SECTIONS_PER_ORG })
                      : t('sidebar.addSection')
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
                  title={t(`sections.metric.${sectionMetric}`)}
                >
                  <MetricIcon metric={sectionMetric} />
                </button>
              </>
            )}
            {activeTab === 'dataHub' && dataHubSubTab === 'apiKeys' && isAdmin && (
              <>
                <button
                  onClick={() => setShowCreateKey(v => !v)}
                  className={`flex items-center justify-center w-6 h-6 rounded transition-colors cursor-pointer ${
                    showCreateKey
                      ? 'text-[var(--proto-text)] bg-[var(--proto-surface-raised)]'
                      : 'text-[var(--proto-text-muted)] hover:text-[var(--proto-text)]'
                  }`}
                  title={t('apiKeys.createKey')}
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
                    const curl = `curl -H "X-API-Key: YOUR_KEY" ${API_URL}/api/v1/fibers`
                    navigator.clipboard.writeText(curl)
                    toast.success(t('apiKeys.curlCopied'))
                  }}
                  className="flex items-center justify-center w-6 h-6 rounded text-[var(--proto-text-muted)] hover:text-[var(--proto-text-secondary)] transition-colors cursor-pointer"
                  title={t('apiKeys.copyCurl')}
                >
                  <svg
                    width="12"
                    height="12"
                    viewBox="0 0 16 16"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  >
                    <path d="M5 4L1 8l4 4M11 4l4 4-4 4" />
                  </svg>
                </button>
              </>
            )}
            {activeTab === 'dataHub' && (
              <a
                href={`${API_URL}/api/v1/docs/`}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center justify-center w-6 h-6 rounded text-[var(--proto-text-muted)] hover:text-[var(--proto-text-secondary)] transition-colors cursor-pointer"
                title={t('userMenu.apiDocs')}
              >
                <svg
                  width="14"
                  height="14"
                  viewBox="0 0 16 16"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d="M4 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2z" />
                  <path d="M5 5h6M5 8h6M5 11h3" />
                </svg>
              </a>
            )}
            <button
              onClick={() => dispatch({ type: 'TOGGLE_SIDEBAR' })}
              className="flex items-center justify-center w-6 h-6 rounded text-[var(--proto-text-muted)] hover:text-[var(--proto-text)] transition-all cursor-pointer"
            >
              <SidebarIcon />
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto">
          {activeTab === 'incidents' && (
            <ErrorBoundary key="incidents" fallback={panelFallback}>
              {incident ? (
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
              )}
            </ErrorBoundary>
          )}
          {activeTab === 'sections' && (
            <ErrorBoundary key="sections" fallback={panelFallback}>
              {section ? (
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
              )}
            </ErrorBoundary>
          )}
          {activeTab === 'settings' && (
            <ErrorBoundary key="settings" fallback={panelFallback}>
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
            </ErrorBoundary>
          )}
          {activeTab === 'channel' && selectedChannel && (
            <ErrorBoundary key="channel" fallback={panelFallback}>
              <ChannelDetail
                channel={selectedChannel}
                sections={sections}
                dispatch={dispatch}
                fiberColors={fiberColors}
              />
            </ErrorBoundary>
          )}
          {activeTab === 'shm' && structureData && (
            <ErrorBoundary key="shm" fallback={panelFallback}>
              {selectedStructureId ? (
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
              )}
            </ErrorBoundary>
          )}
          {activeTab === 'waterfall' && (
            <ErrorBoundary key="waterfall" fallback={panelFallback}>
              <WaterfallPanel />
            </ErrorBoundary>
          )}
          {activeTab === 'dataHub' && (
            <ErrorBoundary key="dataHub" fallback={panelFallback}>
              <DataHubPanel
                subTab={dataHubSubTab}
                isAdmin={isAdmin}
                showCreateKey={showCreateKey}
                onCloseCreateKey={() => setShowCreateKey(false)}
              />
            </ErrorBoundary>
          )}
        </div>
      </div>
    </div>
  )
}
