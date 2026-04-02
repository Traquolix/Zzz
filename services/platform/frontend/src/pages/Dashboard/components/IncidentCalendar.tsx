import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'
import type { CalendarDay } from '@/types/incident'

interface IncidentCalendarProps {
  year: number
  month: number // 1-based
  days: CalendarDay[]
  selectedDate: string | null // YYYY-MM-DD
  loading?: boolean
  error?: boolean
  onSelectDate: (date: string) => void
  onPrevMonth: () => void
  onNextMonth: () => void
}

function getWeekdayLabels(locale: string): string[] {
  const base = new Date(2024, 0, 1) // Monday 2024-01-01
  return Array.from({ length: 7 }, (_, i) => {
    const d = new Date(base)
    d.setDate(base.getDate() + i)
    return d.toLocaleDateString(locale, { weekday: 'narrow' })
  })
}

/**
 * Badge styling based on incident status:
 * - Unread → accent solid (needs attention)
 * - Unresolved (but read) → muted solid (active incidents)
 * - All resolved → outline only (historical)
 */
function badgeClass(day: CalendarDay, isSelected: boolean): string {
  if (isSelected) return 'bg-white/30 text-white'
  if (day.hasUnread) return 'bg-[var(--dash-accent)] text-white'
  if (day.hasUnresolved) return 'bg-[var(--dash-text-muted)] text-[var(--dash-surface)]'
  return 'ring-1 ring-inset ring-[var(--dash-text-muted)]/40 text-[var(--dash-text-muted)]'
}

export function IncidentCalendar({
  year,
  month,
  days,
  selectedDate,
  loading,
  error,
  onSelectDate,
  onPrevMonth,
  onNextMonth,
}: IncidentCalendarProps) {
  const { t, i18n } = useTranslation()

  const monthLabel = new Date(year, month - 1).toLocaleDateString(i18n.language, {
    month: 'long',
    year: 'numeric',
  })

  const weekdays = useMemo(() => getWeekdayLabels(i18n.language), [i18n.language])

  const dayMap = useMemo(() => {
    const m = new Map<string, CalendarDay>()
    for (const d of days) m.set(d.date, d)
    return m
  }, [days])

  const today = new Date().toISOString().slice(0, 10)
  const isViewingCurrentMonth = year === new Date().getFullYear() && month === new Date().getMonth() + 1
  const showTodayButton = selectedDate !== today || !isViewingCurrentMonth

  const cells = useMemo(() => {
    const firstDay = new Date(year, month - 1, 1)
    const lastDay = new Date(year, month, 0).getDate()
    const startOffset = (firstDay.getDay() + 6) % 7

    const result: (number | null)[] = []
    for (let i = 0; i < startOffset; i++) result.push(null)
    for (let d = 1; d <= lastDay; d++) result.push(d)
    // Pad to fill the last row only (5 or 6 rows depending on month)
    while (result.length % 7 !== 0) result.push(null)
    return result
  }, [year, month])

  const handleToday = () => {
    onSelectDate(today)
  }

  return (
    <div className="px-3 py-2.5">
      {/* Month header */}
      <div className="flex items-center justify-between mb-2">
        <button
          onClick={onPrevMonth}
          className="w-6 h-6 flex items-center justify-center rounded text-[var(--dash-text-muted)] hover:text-[var(--dash-text)] hover:bg-[var(--dash-surface-raised)] transition-colors cursor-pointer"
          aria-label="Previous month"
        >
          <svg
            width="10"
            height="10"
            viewBox="0 0 10 10"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M6.5 2L3.5 5L6.5 8" />
          </svg>
        </button>
        <div className="flex items-center gap-2">
          <span className="text-[11px] font-medium text-[var(--dash-text)] capitalize">{monthLabel}</span>
          {loading && (
            <span className="w-3 h-3 rounded-full border-2 border-[var(--dash-text-muted)]/30 border-t-[var(--dash-accent)] animate-spin" />
          )}
          {error && (
            <span className="text-[9px] text-[var(--dash-red)]" title="Failed to load">
              !
            </span>
          )}
          {showTodayButton && (
            <button
              onClick={handleToday}
              className="text-[9px] font-medium px-1.5 py-0.5 rounded bg-[var(--dash-accent)]/15 text-[var(--dash-accent)] hover:bg-[var(--dash-accent)]/25 transition-colors cursor-pointer"
            >
              {t('incidents.calendar.today')}
            </button>
          )}
        </div>
        <button
          onClick={onNextMonth}
          className="w-6 h-6 flex items-center justify-center rounded text-[var(--dash-text-muted)] hover:text-[var(--dash-text)] hover:bg-[var(--dash-surface-raised)] transition-colors cursor-pointer"
          aria-label="Next month"
        >
          <svg
            width="10"
            height="10"
            viewBox="0 0 10 10"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M3.5 2L6.5 5L3.5 8" />
          </svg>
        </button>
      </div>

      {/* Weekday headers */}
      <div className="grid grid-cols-7 mb-0.5">
        {weekdays.map((d, i) => (
          <div
            key={i}
            className="h-5 flex items-center justify-center text-[9px] text-[var(--dash-text-muted)] font-medium uppercase tracking-wider"
          >
            {d}
          </div>
        ))}
      </div>

      {/* Day grid */}
      <div className="grid grid-cols-7">
        {cells.map((day, i) => {
          if (day === null) return <div key={i} className="h-8" />

          const dateStr = `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`
          const dayData = dayMap.get(dateStr)
          const count = dayData?.count ?? 0
          const isToday = dateStr === today
          const isSelected = dateStr === selectedDate

          return (
            <button
              key={i}
              onClick={() => onSelectDate(dateStr)}
              className={cn(
                'h-8 relative flex items-center justify-center rounded-md cursor-pointer transition-all',
                isSelected
                  ? 'bg-[var(--dash-accent)] text-white shadow-sm'
                  : isToday
                    ? 'bg-[var(--dash-accent)]/10 text-[var(--dash-accent)] font-semibold'
                    : 'text-[var(--dash-text-secondary)] hover:bg-[var(--dash-surface-raised)]',
              )}
            >
              <span className="text-[11px] leading-none">{day}</span>
              {count > 0 && dayData && (
                <span
                  className={cn(
                    'absolute -top-0.5 -right-0.5 min-w-[14px] h-[14px] flex items-center justify-center rounded-full text-[8px] font-bold leading-none',
                    badgeClass(dayData, isSelected),
                  )}
                >
                  {count}
                </span>
              )}
            </button>
          )
        })}
      </div>
    </div>
  )
}
