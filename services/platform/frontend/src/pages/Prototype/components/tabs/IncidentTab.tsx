import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'
import { severityColor } from '../../data'
import type { ProtoAction, Severity, ProtoIncident, Section } from '../../types'
import { IncidentList, IncidentDetail } from '../IncidentPanels'

const severityOrder: Severity[] = ['critical', 'high', 'medium', 'low']

interface IncidentTabProps {
  incidents: ProtoIncident[]
  selectedIncidentId: string | null
  filterSeverity: Severity | null
  hideResolved: boolean
  showIncidentsOnMap: boolean
  dispatch: React.Dispatch<ProtoAction>
  onHighlightIncident?: (incidentId: string) => void
  onClearHighlight?: () => void
  unseenIds?: Set<string>
  hasUnseen?: boolean
  onMarkSeen?: (id: string) => void
  onMarkAllSeen?: () => void
  sections: Section[]
}

export function IncidentTabToolbar({
  filterSeverity,
  hideResolved,
  showIncidentsOnMap,
  dispatch,
  hasUnseen,
  onMarkAllSeen,
  incidentSortBy,
  setIncidentSortBy,
}: Pick<
  IncidentTabProps,
  'filterSeverity' | 'hideResolved' | 'showIncidentsOnMap' | 'dispatch' | 'hasUnseen' | 'onMarkAllSeen'
> & {
  incidentSortBy: 'newest' | 'oldest'
  setIncidentSortBy: React.Dispatch<React.SetStateAction<'newest' | 'oldest'>>
}) {
  const { t } = useTranslation()

  return (
    <>
      {filterSeverity && (
        <button
          onClick={() => dispatch({ type: 'SET_FILTER_SEVERITY', severity: null })}
          className="w-3 h-3 rounded-full transition-all cursor-pointer opacity-50 hover:opacity-80 bg-[var(--proto-text-muted)]"
          title={t('incidents.filters.clearFilter')}
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
  )
}

export function IncidentTabContent({
  incidents,
  selectedIncidentId,
  filterSeverity,
  hideResolved,
  dispatch,
  onHighlightIncident,
  onClearHighlight,
  unseenIds,
  onMarkSeen,
  sections,
  sortBy,
}: Omit<IncidentTabProps, 'showIncidentsOnMap' | 'hasUnseen' | 'onMarkAllSeen'> & { sortBy: 'newest' | 'oldest' }) {
  const incident = selectedIncidentId ? incidents.find(i => i.id === selectedIncidentId) : null

  if (incident) {
    return (
      <IncidentDetail
        incident={incident}
        sections={sections}
        dispatch={dispatch}
        onBack={() => dispatch({ type: 'CLEAR_SELECTION' })}
      />
    )
  }

  return (
    <IncidentList
      incidents={incidents}
      filterSeverity={filterSeverity}
      hideResolved={hideResolved}
      sortBy={sortBy}
      dispatch={dispatch}
      onHighlightIncident={onHighlightIncident}
      onClearHighlight={onClearHighlight}
      unseenIds={unseenIds}
      onMarkSeen={onMarkSeen}
    />
  )
}
