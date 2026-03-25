import { useState, useMemo, useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { useQuery } from '@tanstack/react-query'
import { cn } from '@/lib/utils'
import type { PeakFrequencyData, SpectralSummary } from '@/types/infrastructure'
import { fetchPeakFrequencies } from '@/api/infrastructure'
import { useDebouncedResize } from '../hooks/useDebouncedResize'
import { ComparisonOverlay } from './ComparisonOverlay'
import type { ComparisonMode, FocusMode } from './ComparisonOverlay'
import { SHM_FREQ_MIN, SHM_FREQ_MAX } from './shmUtils'

export type ComparisonStats = {
  a: { mean: number; std: number; count: number }
  b: { mean: number; std: number; count: number }
  diff: number
  diffPercent: number
}

export function ComparisonSection({
  dataSummary,
  onStats,
}: {
  dataSummary: SpectralSummary | null
  onStats?: (stats: ComparisonStats | null) => void
}) {
  const { t } = useTranslation()
  const containerRef = useRef<HTMLDivElement>(null)
  const { width: rawChartWidth, transitioning: chartTransitioning } = useDebouncedResize(containerRef)
  const chartWidth = Math.max(160, rawChartWidth)
  const [mode, setMode] = useState<ComparisonMode>('day')
  const [focus, setFocus] = useState<FocusMode>('equal')

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

  // Fetch comparison windows server-side filtered by time range.
  // The backend caches peak data in process memory, so these are cheap
  // (just array slicing, no recomputation). Full resolution per window.
  const queryA = useQuery({
    queryKey: ['shm-peaks-comparison', rangeA.from.getTime(), rangeA.to.getTime()],
    queryFn: () => fetchPeakFrequencies({ startTime: rangeA.from, endTime: rangeA.to }),
    staleTime: Infinity,
  })
  const queryB = useQuery({
    queryKey: ['shm-peaks-comparison', rangeB.from.getTime(), rangeB.to.getTime()],
    queryFn: () => fetchPeakFrequencies({ startTime: rangeB.from, endTime: rangeB.to }),
    staleTime: Infinity,
  })
  const windowA = queryA.data ?? null
  const windowB = queryB.data ?? null

  // Stats
  const stats = useMemo(() => {
    const calc = (d: PeakFrequencyData | null) => {
      if (!d) return null
      const valid = d.peakFrequencies.filter(f => f >= SHM_FREQ_MIN && f <= SHM_FREQ_MAX)
      if (!valid.length) return null
      const mean = valid.reduce((a, b) => a + b, 0) / valid.length
      const variance = valid.reduce((s, f) => s + (f - mean) ** 2, 0) / valid.length
      return { mean, std: Math.sqrt(variance), count: valid.length }
    }
    const a = calc(windowA),
      b = calc(windowB)
    if (!a || !b) return null
    const diff = a.mean - b.mean
    return { a, b, diff, diffPercent: (diff / b.mean) * 100 }
  }, [windowA, windowB])

  const isLoading = queryA.isLoading || queryB.isLoading

  // Expose stats to parent
  useEffect(() => {
    onStats?.(stats)
  }, [stats, onStats])

  return (
    <div>
      {/* Header row */}
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-[length:var(--text-xs)] font-medium text-[var(--dash-text-muted)] uppercase tracking-wider">
          {t('shm.comparison.title')}
        </h3>
        <div className="flex items-center gap-2">
          {/* Mode selector */}
          <select
            value={mode}
            onChange={e => setMode(e.target.value as ComparisonMode)}
            className="text-[length:var(--text-2xs)] bg-[var(--dash-surface-raised)] text-[var(--dash-text-secondary)] border border-[var(--dash-border)] rounded px-1.5 py-0.5 cursor-pointer"
          >
            <option value="day">{t('shm.comparison.dayOverDay')}</option>
            <option value="week">{t('shm.comparison.weekOverWeek')}</option>
          </select>
          {/* Focus toggle */}
          <div className="flex items-center bg-[var(--dash-surface-raised)] rounded p-0.5 border border-[var(--dash-border)]">
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
                        : 'bg-[var(--dash-text-muted)] text-white'
                    : 'text-[var(--dash-text-muted)] hover:text-[var(--dash-text)]',
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
          <span className="text-[var(--dash-text-secondary)]">{t('shm.comparison.labelA', { date: labelA })}</span>
        </div>
        <span className="text-[var(--dash-text-muted)]">{t('shm.comparison.vs')}</span>
        <div className="flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-full bg-amber-500 shrink-0" />
          <span className="text-[var(--dash-text-secondary)]">{t('shm.comparison.labelB', { date: labelB })}</span>
        </div>
      </div>

      {/* Chart */}
      <div
        ref={containerRef}
        className="rounded-lg bg-[var(--dash-surface-raised)] border border-[var(--dash-border)] p-2"
      >
        {isLoading || chartTransitioning ? (
          <div className="flex items-center justify-center h-[140px]">
            {isLoading ? (
              <div className="w-4 h-4 border-2 border-[var(--dash-text-muted)] border-t-transparent rounded-full animate-spin" />
            ) : (
              <div className="w-full h-full rounded-lg bg-[var(--dash-surface-raised)] animate-pulse" />
            )}
          </div>
        ) : (
          <ComparisonOverlay dataA={windowA} dataB={windowB} focus={focus} width={chartWidth} />
        )}
      </div>

      {/* Stats (A/B mean and σ only — shift banner is in StructureDetail) */}
      {stats && (
        <div className="mt-2">
          <div className="grid grid-cols-2 gap-2 text-[length:var(--text-2xs)]">
            <div className="flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-blue-500" />
              <span className="text-[var(--dash-text-muted)]">μ</span>
              <span className="text-[var(--dash-text-secondary)]">
                {stats.a.mean.toFixed(4)} {t('shm.hzUnit')}
              </span>
              <span className="text-[var(--dash-text-muted)]">(σ={stats.a.std.toFixed(4)})</span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-amber-500" />
              <span className="text-[var(--dash-text-muted)]">μ</span>
              <span className="text-[var(--dash-text-secondary)]">
                {stats.b.mean.toFixed(4)} {t('shm.hzUnit')}
              </span>
              <span className="text-[var(--dash-text-muted)]">(σ={stats.b.std.toFixed(4)})</span>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
