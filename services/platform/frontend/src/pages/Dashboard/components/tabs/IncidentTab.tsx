import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { useQuery } from '@tanstack/react-query'
import { cn } from '@/lib/utils'
import { severityColor } from '@/lib/theme'
import type { CalendarDay, Incident } from '@/types/incident'
import type { Severity, DisplayIncident, Section } from '../../types'
import { IncidentList, IncidentDetail } from '../IncidentPanels'
import { IncidentCalendar } from '../IncidentCalendar'
import { useDashboard } from '../../context/DashboardContext'
import { useRealtime } from '@/hooks/useRealtime'
import { fetchIncidents, fetchIncidentCalendar } from '@/api/incidents'

const severityOrder: Severity[] = ['critical', 'high', 'medium', 'low']

function toYMD(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

function formatDateShort(dateStr: string, locale: string): string {
  const d = new Date(dateStr + 'T00:00:00')
  return d.toLocaleDateString(locale, { month: 'short', day: 'numeric' })
}

interface IncidentTabProps {
  incidents: DisplayIncident[]
  selectedIncidentId: string | null
  filterSeverity: Severity | null
  hideResolved: boolean
  showIncidentsOnMap: boolean
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
  hasUnseen,
  onMarkAllSeen,
  incidentSortBy,
  setIncidentSortBy,
  selectedDate,
  onToggleCalendar,
}: Pick<IncidentTabProps, 'filterSeverity' | 'hideResolved' | 'showIncidentsOnMap' | 'hasUnseen' | 'onMarkAllSeen'> & {
  incidentSortBy: 'newest' | 'oldest'
  setIncidentSortBy: React.Dispatch<React.SetStateAction<'newest' | 'oldest'>>
  selectedDate: string
  onToggleCalendar: () => void
}) {
  const { dispatch } = useDashboard()
  const { t, i18n } = useTranslation()
  const isToday = selectedDate === toYMD(new Date())

  return (
    <>
      <button
        onClick={onToggleCalendar}
        className={cn(
          'px-1.5 py-0.5 rounded text-[10px] font-medium transition-colors cursor-pointer',
          isToday
            ? 'bg-[var(--dash-accent)]/20 text-[var(--dash-accent)]'
            : 'bg-[var(--dash-surface-raised)] text-[var(--dash-text)]',
        )}
      >
        {isToday ? t('incidents.calendar.today') : formatDateShort(selectedDate, i18n.language)}
      </button>
      {filterSeverity && (
        <button
          onClick={() => dispatch({ type: 'SET_FILTER_SEVERITY', severity: null })}
          className="w-3 h-3 rounded-full transition-all cursor-pointer opacity-50 hover:opacity-80 bg-[var(--dash-text-muted)]"
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
            className="text-[var(--dash-surface)]"
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
            'w-3 h-3 rounded-full transition-all cursor-pointer ring-offset-1 ring-offset-[var(--dash-surface)]',
            filterSeverity === s ? 'ring-1 ring-[var(--dash-text-secondary)] scale-125' : 'opacity-50 hover:opacity-80',
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
            ? 'text-[var(--dash-text-muted)] hover:text-[var(--dash-text-secondary)]'
            : 'text-[var(--dash-accent)]',
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
            ? 'text-[var(--dash-accent)]'
            : 'text-[var(--dash-text-muted)] hover:text-[var(--dash-text-secondary)]',
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
        className="flex items-center justify-center w-6 h-6 rounded text-[var(--dash-text-muted)] hover:text-[var(--dash-text)] transition-colors cursor-pointer"
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
          className="flex items-center justify-center w-6 h-6 rounded text-[var(--dash-text-muted)] hover:text-[var(--dash-text)] transition-colors cursor-pointer"
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
  onHighlightIncident,
  onClearHighlight,
  unseenIds,
  onMarkSeen,
  sections,
  sortBy,
  toDisplayIncident,
  calendar,
}: Omit<IncidentTabProps, 'showIncidentsOnMap' | 'hasUnseen' | 'onMarkAllSeen'> & {
  sortBy: 'newest' | 'oldest'
  toDisplayIncident: (inc: Incident) => DisplayIncident
  calendar: {
    open: boolean
    selectedDate: string
    year: number
    month: number
    onSelectDate: (date: string) => void
    onPrevMonth: () => void
    onNextMonth: () => void
  }
}) {
  const { dispatch } = useDashboard()
  const { t } = useTranslation()
  const { flow } = useRealtime()
  const today = toYMD(new Date())
  const isToday = calendar.selectedDate === today

  // Calendar counts from API (fetched when calendar is open)
  const monthStr = `${calendar.year}-${String(calendar.month).padStart(2, '0')}`
  const {
    data: apiDays = [],
    isLoading: calendarLoading,
    isError: calendarError,
  } = useQuery({
    queryKey: ['incident-calendar', monthStr, flow],
    queryFn: () => fetchIncidentCalendar(monthStr, flow),
    enabled: calendar.open,
    staleTime: 60_000,
  })

  // Enrich API calendar data with live incident status (unread/unresolved)
  const calendarDays: CalendarDay[] = useMemo(() => {
    // Group in-memory incidents by date for status enrichment
    const byDate = new Map<string, { count: number; hasUnresolved: boolean; hasUnread: boolean }>()
    for (const inc of incidents) {
      const day = inc.detectedAt.slice(0, 10)
      const entry = byDate.get(day) ?? { count: 0, hasUnresolved: false, hasUnread: false }
      entry.count++
      if (!inc.resolved) entry.hasUnresolved = true
      if (unseenIds?.has(inc.id)) entry.hasUnread = true
      byDate.set(day, entry)
    }

    // Start with API data, override with live data where available
    const merged = new Map<string, CalendarDay>()
    for (const d of apiDays) merged.set(d.date, d)
    for (const [date, live] of byDate) {
      const existing = merged.get(date)
      merged.set(date, {
        date,
        count: Math.max(existing?.count ?? 0, live.count),
        hasUnresolved: live.hasUnresolved,
        hasUnread: live.hasUnread,
      })
    }
    return Array.from(merged.values())
  }, [apiDays, incidents, unseenIds])

  // Past day incidents: fetch from API and transform, cached per date
  const { data: pastDayIncidents, isLoading: pastDayLoading } = useQuery({
    queryKey: ['incidents-by-date', calendar.selectedDate, flow],
    queryFn: async () => {
      const res = await fetchIncidents(flow, calendar.selectedDate)
      return res.results.map(toDisplayIncident)
    },
    enabled: !isToday,
    staleTime: 5 * 60_000, // 5 min — past incidents may still get resolved
  })

  const displayIncidents = isToday ? incidents.filter(i => i.detectedAt.startsWith(today)) : (pastDayIncidents ?? [])

  const incident = selectedIncidentId ? displayIncidents.find(i => i.id === selectedIncidentId) : null

  if (incident) {
    return (
      <IncidentDetail incident={incident} sections={sections} onBack={() => dispatch({ type: 'CLEAR_SELECTION' })} />
    )
  }

  return (
    <>
      {calendar.open && (
        <div className="border-b border-[var(--dash-border)]">
          <IncidentCalendar
            year={calendar.year}
            month={calendar.month}
            days={calendarDays}
            selectedDate={calendar.selectedDate}
            loading={calendarLoading}
            error={calendarError}
            onSelectDate={calendar.onSelectDate}
            onPrevMonth={calendar.onPrevMonth}
            onNextMonth={calendar.onNextMonth}
          />
        </div>
      )}
      {!isToday && pastDayLoading && (
        <div className="flex items-center justify-center py-8 text-[var(--dash-text-muted)] text-cq-xs">
          <span className="w-4 h-4 rounded-full border-2 border-[var(--dash-text-muted)]/30 border-t-[var(--dash-accent)] animate-spin mr-2" />
          {t('common.loading')}
        </div>
      )}
      <IncidentList
        incidents={displayIncidents}
        filterSeverity={filterSeverity}
        hideResolved={hideResolved}
        sortBy={sortBy}
        onHighlightIncident={onHighlightIncident}
        onClearHighlight={onClearHighlight}
        unseenIds={unseenIds}
        onMarkSeen={onMarkSeen}
      />
    </>
  )
}
