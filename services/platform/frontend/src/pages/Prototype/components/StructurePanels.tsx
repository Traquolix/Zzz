import { useState, useMemo, useEffect, useRef, useCallback } from 'react'
import { useQuery } from '@tanstack/react-query'
import { cn } from '@/lib/utils'
import { findFiber } from '../data'
import type { ProtoAction } from '../types'
import type {
  Infrastructure,
  SHMStatus,
  SpectralTimeSeries,
  PeakFrequencyData,
  SpectralSummary,
} from '@/types/infrastructure'
import { fetchPeakFrequencies } from '@/api/infrastructure'
import { useDebouncedResize } from '../hooks/useDebouncedResize'
import { SpectralHeatmapCanvas, PeakScatterPlot, ComparisonOverlay } from './ShmCharts'

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

// ── Comparison section ───────────────────────────────────────────────

type ComparisonMode = 'day' | 'week'
type FocusMode = 'A' | 'equal' | 'B'

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
      const valid = d.peakFrequencies.filter(f => f >= 1.05 && f <= 1.2)
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
          <ComparisonOverlay dataA={windowA} dataB={windowB} focus={focus} width={chartWidth} />
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

export { StructureList, StructureDetail }
