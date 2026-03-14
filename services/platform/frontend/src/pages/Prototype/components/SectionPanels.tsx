import { useState, useEffect } from 'react'
import { cn } from '@/lib/utils'
import { chartColors, findFiber, getSpeedColor, getFiberColor } from '../data'
import type { ProtoAction, Section, LiveSectionStats, SectionDataPoint, MetricKey, SpeedThresholds } from '../types'
import { TimeSeriesChart } from './TimeSeriesChart'
import { Sparkline } from './Sparkline'
import { useSectionHistory } from '../hooks/useSectionHistory'

type TimeRange = '1m' | '5m' | '15m' | '1h'

export function computeTrend(history: number[]): { pct: number } {
  if (history.length < 10) return { pct: 0 }
  const recent = history.slice(-5)
  const earlier = history.slice(0, 5)
  const avgRecent = recent.reduce((a, b) => a + b, 0) / recent.length
  const avgEarlier = earlier.reduce((a, b) => a + b, 0) / earlier.length
  const delta = avgRecent - avgEarlier
  const pct = avgEarlier !== 0 ? Math.round((delta / avgEarlier) * 100) : 0
  return { pct }
}

export function TrendBadge({ pct, positiveIsGood }: { pct: number; positiveIsGood: boolean }) {
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

export function ThresholdEditor({
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

// ── Section list ────────────────────────────────────────────────────────

export function SectionList({
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

// ── Section detail ──────────────────────────────────────────────────────

export function SectionDetail({
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

  // KPIs use the always-on page-level stats (stable regardless of chart time range)
  const live = liveStats.get(section.id)
  const liveSeries = liveSeriesData.get(section.id)

  // Chart data: at 1m reuses batch data from useLiveStats (no extra request),
  // at longer ranges fetches independently.
  const { series: historySeries, stale: historyStale } = useSectionHistory(section.id, timeRange, liveSeries)
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
          <div
            className={historyStale ? 'opacity-50 transition-opacity duration-200' : 'transition-opacity duration-200'}
          >
            <TimeSeriesChart data={chartData} timeRange={timeRange} />
          </div>
        </div>

        {/* Data table */}
        <div
          className={`border-t border-[var(--proto-border)] pt-3 ${historyStale ? 'opacity-50 transition-opacity duration-200' : 'transition-opacity duration-200'}`}
        >
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
