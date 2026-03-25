import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import i18next from 'i18next'
import { useAuth } from '@/hooks/useAuth'
import { cn } from '@/lib/utils'
import type { MapPageState, MapPageAction, LiveSectionStats, SectionDataPoint } from '../types'
import { useRealtime } from '@/hooks/useRealtime'
import { ErrorBoundary } from '@/components/ui/ErrorBoundary'
import { WaterfallPanel } from './WaterfallPanel'
import { ChannelDetail } from './ChannelDetail'
import { SettingsPanel } from './SettingsPanel'
import {
  TabButton,
  SidebarIcon,
  IncidentsIcon,
  SectionsIcon,
  ExpandIcon,
  SettingsIcon,
  BridgeIcon,
  ChannelIcon,
  DataHubIcon,
} from './SidebarIcons'
import { IncidentTabToolbar, IncidentTabContent } from './tabs/IncidentTab'
import { SectionTabToolbar, SectionTabContent } from './tabs/SectionTab'
import { ShmTabToolbar, ShmTabContent } from './tabs/ShmTab'
import type { InfrastructureData } from '../hooks/useInfrastructure'
import { DataHubTabToolbar, DataHubTabContent } from './tabs/DataHubTab'
import type { DataHubSubTab } from './DataHubPanel'

interface SidePanelProps {
  state: MapPageState
  dispatch: React.Dispatch<MapPageAction>
  panelRef: React.RefObject<HTMLDivElement | null>
  liveStats: Map<string, LiveSectionStats>
  liveSeriesData: Map<string, SectionDataPoint[]>
  onHighlightFiber?: (fiberId: string) => void
  onHighlightSection?: (sectionId: string) => void
  onHighlightIncident?: (incidentId: string) => void
  onClearHighlight?: () => void
  infrastructure: InfrastructureData
  unseenIds?: Set<string>
  hasUnseen?: boolean
  onMarkSeen?: (id: string) => void
  onMarkAllSeen?: () => void
}

/** Compact fallback UI for panel-level error boundaries. */
const panelFallback = (retry: () => void) => (
  <div className="flex flex-col items-center justify-center gap-3 py-12 px-4 text-center">
    <svg
      width="28"
      height="28"
      viewBox="0 0 24 24"
      fill="none"
      stroke="var(--dash-text-muted)"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
    </svg>
    <span className="text-cq-sm text-[var(--dash-text-muted)]">{i18next.t('common.somethingWentWrong')}</span>
    <button
      onClick={retry}
      className="px-3 py-1.5 rounded text-cq-xs font-medium text-[var(--dash-text-secondary)] bg-[var(--dash-surface-raised)] hover:text-[var(--dash-text)] transition-colors cursor-pointer"
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
  infrastructure,
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

  // Per-tab local state
  const [incidentSortBy, setIncidentSortBy] = useState<'newest' | 'oldest'>('newest')
  const [shmSearch, setShmSearch] = useState('')
  const [sectionSearch, setSectionSearch] = useState('')
  const [dataHubSubTab, setDataHubSubTab] = useState<DataHubSubTab>('export')
  const [showCreateKey, setShowCreateKey] = useState(false)

  // Track when the slide transition finishes so we can delay showing/hiding elements
  const [fullyClosed, setFullyClosed] = useState(!sidebarOpen)

  useEffect(() => {
    if (sidebarOpen) setFullyClosed(false)
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
          aria-label={t('sidebar.toggleSidebar')}
          className="absolute top-3 right-3 z-30 flex items-center justify-center w-9 h-9 rounded-lg bg-[var(--dash-surface)] border border-[var(--dash-border)] text-[var(--dash-text-muted)] hover:text-[var(--dash-text)] hover:border-[var(--dash-text-muted)]/30 transition-all cursor-pointer pointer-events-auto"
        >
          <SidebarIcon />
          {hasUnseen && (
            <span className="absolute -top-1 -right-1 w-2.5 h-2.5 rounded-full bg-[var(--dash-red)] border-2 border-[var(--dash-surface)]" />
          )}
        </button>
      )}

      {/* Main panel — slides in/out via transform, tabs ride along */}
      <div
        ref={panelRef}
        className={cn(
          'dash-sidebar h-full flex flex-col bg-[var(--dash-surface)] border-l border-[var(--dash-border)] shadow-[-4px_0_16px_rgba(0,0,0,0.3)] pointer-events-auto',
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
          <div className="flex flex-col gap-1.5 mt-8" role="tablist" aria-label={t('sidebar.tablistLabel')}>
            <TabButton
              label={t('sidebar.tabs.sections')}
              icon={<SectionsIcon />}
              active={activeTab === 'sections'}
              onClick={() => dispatch({ type: 'SET_TAB', tab: 'sections' })}
            />
            <TabButton
              label={t('sidebar.tabs.incidents')}
              icon={<IncidentsIcon />}
              active={activeTab === 'incidents'}
              onClick={() => dispatch({ type: 'SET_TAB', tab: 'incidents' })}
              showDot={hasUnseen}
            />
            <TabButton
              label={t('sidebar.tabs.shm')}
              icon={<BridgeIcon />}
              active={activeTab === 'shm'}
              onClick={() => dispatch({ type: 'SET_TAB', tab: 'shm' })}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <button
              title={sidebarExpanded ? t('sidebar.collapsePanel') : t('sidebar.expandPanel')}
              aria-label={sidebarExpanded ? t('sidebar.collapsePanel') : t('sidebar.expandPanel')}
              aria-expanded={!!sidebarExpanded}
              onClick={() => dispatch({ type: 'TOGGLE_SIDEBAR_EXPANDED' })}
              className="group/exp flex items-center justify-center self-end w-[32px] hover:w-full h-7 rounded-l-lg border border-r-0 border-transparent bg-[var(--dash-surface)]/40 text-[var(--dash-text-muted)] hover:text-[var(--dash-text-secondary)] hover:bg-[var(--dash-surface)]/80 transition-all cursor-pointer"
            >
              <ExpandIcon expanded={!!sidebarExpanded} />
            </button>
            {selectedChannel && (
              <TabButton
                label={t('sidebar.tabs.channel')}
                icon={<ChannelIcon />}
                active={activeTab === 'channel'}
                onClick={() => dispatch({ type: 'SELECT_CHANNEL', channel: selectedChannel })}
              />
            )}
            {activeTab === 'settings' && (
              <TabButton
                label={t('sidebar.tabs.settings')}
                icon={<SettingsIcon />}
                active
                onClick={() => dispatch({ type: 'SET_TAB', tab: 'settings' })}
              />
            )}
            {activeTab === 'dataHub' && (
              <TabButton
                label={t('sidebar.tabs.dataHub')}
                icon={<DataHubIcon />}
                active
                onClick={() => dispatch({ type: 'SET_TAB', tab: 'dataHub' })}
              />
            )}
          </div>
        </div>

        {/* Panel header */}
        <div className="flex items-center justify-between px-4 h-[52px] shrink-0 border-b border-[var(--dash-border)]">
          <div className="flex items-center gap-3">
            <span className="text-cq-sm font-medium text-[var(--dash-text-muted)] uppercase tracking-wider">
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
                    className={`relative px-2 py-1 text-cq-xxs font-medium transition-colors cursor-pointer rounded ${
                      dataHubSubTab === tab
                        ? 'text-[var(--dash-text)] bg-[var(--dash-surface-raised)]'
                        : 'text-[var(--dash-text-muted)] hover:text-[var(--dash-text-secondary)]'
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
              <IncidentTabToolbar
                filterSeverity={filterSeverity}
                hideResolved={hideResolved}
                showIncidentsOnMap={showIncidentsOnMap}
                dispatch={dispatch}
                hasUnseen={hasUnseen}
                onMarkAllSeen={onMarkAllSeen}
                incidentSortBy={incidentSortBy}
                setIncidentSortBy={setIncidentSortBy}
              />
            )}
            {activeTab === 'shm' && (
              <ShmTabToolbar
                shmSearch={shmSearch}
                setShmSearch={setShmSearch}
                showStructuresOnMap={showStructuresOnMap}
                showStructureLabels={showStructureLabels}
                dispatch={dispatch}
              />
            )}
            {activeTab === 'sections' && !selectedSectionId && (
              <SectionTabToolbar
                sectionSearch={sectionSearch}
                setSectionSearch={setSectionSearch}
                sections={sections}
                sectionMetric={sectionMetric}
                dispatch={dispatch}
              />
            )}
            {activeTab === 'dataHub' && (
              <DataHubTabToolbar
                dataHubSubTab={dataHubSubTab}
                showCreateKey={showCreateKey}
                setShowCreateKey={setShowCreateKey}
                isAdmin={isAdmin}
              />
            )}
            <button
              onClick={() => dispatch({ type: 'TOGGLE_SIDEBAR' })}
              aria-label={t('sidebar.toggleSidebar')}
              className="flex items-center justify-center w-6 h-6 rounded text-[var(--dash-text-muted)] hover:text-[var(--dash-text)] transition-all cursor-pointer"
            >
              <SidebarIcon />
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto" role="tabpanel" id={`panel-${activeTab}`}>
          {activeTab === 'incidents' && (
            <ErrorBoundary key="incidents" fallback={panelFallback}>
              <IncidentTabContent
                incidents={incidents}
                selectedIncidentId={selectedIncidentId}
                filterSeverity={filterSeverity}
                hideResolved={hideResolved}
                dispatch={dispatch}
                onHighlightIncident={onHighlightIncident}
                onClearHighlight={onClearHighlight}
                unseenIds={unseenIds}
                onMarkSeen={onMarkSeen}
                sections={sections}
                sortBy={incidentSortBy}
              />
            </ErrorBoundary>
          )}
          {activeTab === 'sections' && (
            <ErrorBoundary key="sections" fallback={panelFallback}>
              <SectionTabContent
                sections={sections}
                selectedSectionId={selectedSectionId}
                dispatch={dispatch}
                liveStats={liveStats}
                liveSeriesData={liveSeriesData}
                sectionMetric={sectionMetric}
                fiberColors={fiberColors}
                onHighlightSection={onHighlightSection}
                onClearHighlight={onClearHighlight}
                search={sectionSearch}
              />
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
          {activeTab === 'shm' && (
            <ErrorBoundary key="shm" fallback={panelFallback}>
              <ShmTabContent
                structures={infrastructure.structures}
                loading={infrastructure.loading}
                allStatuses={infrastructure.allStatuses}
                selectedStructureId={selectedStructureId}
                dispatch={dispatch}
                onHighlightSection={onHighlightSection}
                onClearHighlight={onClearHighlight}
                search={shmSearch}
              />
            </ErrorBoundary>
          )}
          {activeTab === 'waterfall' && (
            <ErrorBoundary key="waterfall" fallback={panelFallback}>
              <WaterfallPanel />
            </ErrorBoundary>
          )}
          {activeTab === 'dataHub' && (
            <ErrorBoundary key="dataHub" fallback={panelFallback}>
              <DataHubTabContent
                dataHubSubTab={dataHubSubTab}
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
