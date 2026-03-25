import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'
import { COLORS, chartColors } from '@/lib/theme'
import { findFiber, getSpeedColor, getFiberColor } from '../data'
import type { MapPageAction, Section, LiveSectionStats, SectionDataPoint, MetricKey } from '../types'
import { TimeSeriesChart } from './TimeSeriesChart'
import { Sparkline } from './Sparkline'
import { useSectionHistory } from '../hooks/useSectionHistory'
import { PanelEmptyState } from './PanelEmptyState'
import { DetailHeader } from './DetailHeader'
import { MetricCard } from './MetricCard'

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
    <span className={cn('text-cq-2xs ml-1', isGood ? 'text-green-400' : 'text-red-400')}>
      {isUp ? '\u2191' : '\u2193'}
      {Math.abs(pct)}%
    </span>
  )
}

import { ThresholdEditor } from './ThresholdEditor'
export { ThresholdEditor }

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
  dispatch: React.Dispatch<MapPageAction>
  liveStats: Map<string, LiveSectionStats>
  liveSeriesData: Map<string, SectionDataPoint[]>
  metric: MetricKey
  fiberColors: Record<string, string>
  onHighlightSection?: (id: string) => void
  onClearHighlight?: () => void
  search?: string
}) {
  const { t } = useTranslation()
  const metricConfig = chartColors[metric]
  const query = search?.trim().toLowerCase() ?? ''
  const filtered = query
    ? sections.filter(s => s.name.toLowerCase().includes(query) || s.fiberId.toLowerCase().includes(query))
    : sections

  return (
    <>
      {sections.length === 0 ? (
        <PanelEmptyState message={t('traffic.empty.noSections')} />
      ) : filtered.length === 0 ? (
        <PanelEmptyState message={t('sections.noMatchingSections')} />
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
                  className="w-full text-left px-3 py-2.5 rounded-lg hover:bg-[var(--dash-surface-raised)] transition-colors cursor-pointer"
                >
                  <div className="flex items-center gap-2 mb-1">
                    <span
                      className="shrink-0 w-2 h-2 rounded-full"
                      style={{ backgroundColor: fiber ? getFiberColor(fiber, fiberColors) : undefined }}
                    />
                    <span className="text-cq-sm text-[var(--dash-text)] font-medium truncate">{section.name}</span>
                  </div>
                  <div className="flex items-center justify-between text-cq-xs text-[var(--dash-text-secondary)] pl-4">
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
                  className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 text-[var(--dash-text-muted)] hover:text-[var(--dash-red)] transition-all text-cq-xs cursor-pointer px-1"
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
  dispatch: React.Dispatch<MapPageAction>
  fiberColors: Record<string, string>
}) {
  const { t } = useTranslation()
  const fiber = findFiber(section.fiberId, section.direction)
  const fiberColor = fiber ? getFiberColor(fiber, fiberColors) : COLORS.chart.speed

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
      label: t('sections.kpi.avgSpeed'),
      value: `${displaySpeed}`,
      unit: 'km/h',
      trend: speedSpark,
      color: COLORS.chart.speed,
      trendPct: speedTrend.pct,
      positiveIsGood: true,
    },
    {
      label: t('sections.kpi.flow'),
      value: `${displayFlow}`,
      unit: 'veh/h',
      trend: flowSpark,
      color: COLORS.chart.flow,
      trendPct: flowTrend.pct,
      positiveIsGood: true,
    },
    {
      label: t('sections.kpi.occupancy'),
      value: `${displayOccupancy}`,
      unit: '%',
      trend: occupancySpark,
      color: COLORS.chart.occupancy,
    },
    { label: t('sections.kpi.travelTime'), value: `${displayTravelTime}`, unit: 'min', color: fiberColor },
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
    <div className="dash-analysis-enter flex flex-col">
      <DetailHeader
        title={section.name}
        onBack={onBack}
        subtitle={
          fiber && (
            <span className="text-cq-2xs text-[var(--dash-text-muted)] flex items-center gap-1.5">
              <span
                className="inline-block w-2 h-2 rounded-full flex-shrink-0"
                style={{ backgroundColor: fiberColor }}
              />
              {fiber.name} · {fiber.direction === 0 ? 'Dir A' : 'Dir B'} · Ch {section.startChannel}–
              {section.endChannel}
            </span>
          )
        }
      />

      <div className="px-4 py-4 flex flex-col gap-3">
        {/* KPI grid */}
        <div className="grid grid-cols-2 gap-3">
          {kpis.map(kpi => (
            <MetricCard
              key={kpi.label}
              label={kpi.label}
              value={kpi.value}
              unit={kpi.unit}
              labelExtra={
                kpi.trendPct !== undefined && (
                  <TrendBadge pct={kpi.trendPct} positiveIsGood={kpi.positiveIsGood ?? true} />
                )
              }
            >
              {kpi.trend && <Sparkline data={kpi.trend} color={kpi.color} width={48} height={20} />}
            </MetricCard>
          ))}
        </div>

        {/* Time series chart */}
        <div className="border-t border-[var(--dash-border)] pt-3">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-cq-xs font-medium text-[var(--dash-text-muted)] uppercase tracking-wider">
              {t('sections.timeSeries')}
            </h3>
            <div className="flex gap-1">
              {(['1m', '5m', '15m', '1h'] as TimeRange[]).map(r => (
                <button
                  key={r}
                  onClick={() => setTimeRange(r)}
                  className={cn(
                    'px-2 py-0.5 rounded text-cq-2xs transition-colors cursor-pointer',
                    timeRange === r
                      ? 'bg-[var(--dash-accent)] text-white'
                      : 'bg-[var(--dash-surface)] text-[var(--dash-text-muted)] hover:text-[var(--dash-text)]',
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
          className={`border-t border-[var(--dash-border)] pt-3 ${historyStale ? 'opacity-50 transition-opacity duration-200' : 'transition-opacity duration-200'}`}
        >
          <h3 className="text-cq-xs font-medium text-[var(--dash-text-muted)] uppercase tracking-wider mb-3">
            {t('sections.recentData')}
          </h3>
          <div className="overflow-x-auto">
            <table className="w-full text-cq-xs">
              <thead>
                <tr className="text-[var(--dash-text-muted)] border-b border-[var(--dash-border)]">
                  <th className="text-left py-1.5 pr-3 font-medium">{t('sections.table.time')}</th>
                  <th className="text-right py-1.5 px-3 font-medium">{t('sections.table.speed')}</th>
                  <th className="text-right py-1.5 px-3 font-medium">{t('sections.table.flow')}</th>
                  <th className="text-right py-1.5 pl-3 font-medium">{t('sections.table.occupancy')}</th>
                </tr>
              </thead>
              <tbody>
                {tableData.map((row, i) => (
                  <tr key={i} className="border-b border-[var(--dash-border)] text-[var(--dash-text-secondary)]">
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
          onChange={th => dispatch({ type: 'UPDATE_SECTION_THRESHOLDS', id: section.id, thresholds: th })}
        />
      </div>
    </div>
  )
}
