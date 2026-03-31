import { useState, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { useFiberData } from '../context/FiberContext'
import { useDashboard } from '../context/DashboardContext'
import { PanelEmptyState } from './PanelEmptyState'
import { DetailHeader } from './DetailHeader'
import { MetricCard } from './MetricCard'
import { DetailSection } from './DetailSection'
import { StatusBadge } from './StatusBadge'
import { ColorDot } from './ColorDot'
import type {
  Infrastructure,
  SHMStatus,
  SpectralTimeSeries,
  PeakFrequencyData,
  SpectralSummary,
} from '@/types/infrastructure'
import { SpectralHeatmapCanvas, PeakScatterPlot } from './ShmCharts'
import { ComparisonSection, type ComparisonStats } from './ComparisonSection'
import { COLORS, structureTypeColors, shmStatusColors } from '@/lib/theme'

// ── Structure list ───────────────────────────────────────────────────

function StructureList({
  structures,
  loading,
  allStatuses,
  search,
  onHighlightSection,
  onClearHighlight,
}: {
  structures: Infrastructure[]
  loading: boolean
  allStatuses: Map<string, SHMStatus>
  search: string
  onHighlightSection?: (sectionId: string) => void
  onClearHighlight?: () => void
}) {
  const { dispatch } = useDashboard()
  const { t } = useTranslation()
  const { findFiber } = useFiberData()

  if (loading) {
    return <PanelEmptyState message={t('shm.loadingStructures')} loading />
  }

  if (structures.length === 0) {
    return <PanelEmptyState message={t('shm.noInfrastructure')} />
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
        <div className="flex items-center justify-center h-24 text-[var(--dash-text-muted)] text-cq-sm">
          {t('shm.noMatchingStructures', { search })}
        </div>
      ) : (
        filtered.map(structure => {
          const typeStyle = structureTypeColors[structure.type] ?? structureTypeColors.bridge
          const fiber = findFiber(structure.fiberId, structure.direction ?? 0)
          const status = allStatuses.get(structure.id)
          const dotColor = status ? (shmStatusColors[status.status] ?? COLORS.shmChart.axis) : COLORS.shmChart.axis

          return (
            <button
              key={structure.id}
              onClick={() => dispatch({ type: 'SELECT_STRUCTURE', id: structure.id })}
              onMouseEnter={() => onHighlightSection?.(structure.id)}
              onMouseLeave={() => onClearHighlight?.()}
              className="w-full text-left px-3 py-2 rounded-lg hover:bg-[var(--dash-surface-raised)] transition-colors cursor-pointer"
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
                  <span className="text-cq-sm text-[var(--dash-text)] font-medium truncate">{structure.name}</span>
                  <ColorDot color={dotColor} />
                </div>
                <span className="text-cq-xs text-[var(--dash-text-muted)] shrink-0">
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
  const { t } = useTranslation()
  const { findFiber } = useFiberData()
  const [comparisonStats, setComparisonStats] = useState<ComparisonStats | null>(null)
  const handleComparisonStats = useCallback((s: ComparisonStats | null) => setComparisonStats(s), [])

  if (!structure) {
    return <PanelEmptyState message={t('shm.structureNotFound')} />
  }

  const typeStyle = structureTypeColors[structure.type] ?? structureTypeColors.bridge
  const fiber = findFiber(structure.fiberId, structure.direction ?? 0)
  const statusColor = shmStatus ? (shmStatusColors[shmStatus.status] ?? shmStatusColors.nominal) : COLORS.shmChart.axis

  const kpis = [
    { label: t('shm.kpi.peakFreq'), value: shmStatus ? `${shmStatus.currentMean.toFixed(1)}` : '--', unit: 'Hz' },
    { label: t('shm.kpi.baseline'), value: shmStatus ? `${shmStatus.baselineMean.toFixed(1)}` : '--', unit: 'Hz' },
    { label: t('shm.kpi.deviation'), value: shmStatus ? `${shmStatus.deviationSigma.toFixed(2)}` : '--', unit: 'σ' },
    { label: t('shm.kpi.status'), value: shmStatus?.status ?? '--', unit: '', isStatus: true },
  ]

  return (
    <div className="dash-analysis-enter flex flex-col">
      <DetailHeader
        title={structure.name}
        onBack={onBack}
        subtitle={
          fiber && (
            <span className="text-cq-2xs text-[var(--dash-text-muted)] flex items-center gap-1.5">
              <ColorDot color={typeStyle.dot} />
              {structure.type} · {fiber.name} · Ch {structure.startChannel}–{structure.endChannel}
            </span>
          )
        }
        badge={shmStatus && <StatusBadge label={shmStatus.status} color={statusColor} />}
      />

      <div className="px-4 py-4 flex flex-col gap-3">
        {/* Image */}
        {structure.imageUrl && (
          <img
            src={structure.imageUrl}
            alt={structure.name}
            className="w-full max-h-32 object-cover rounded-lg border border-[var(--dash-border)]"
          />
        )}

        {/* KPI grid */}
        <div className="grid grid-cols-2 gap-3">
          {kpis.map(kpi => (
            <MetricCard
              key={kpi.label}
              label={kpi.label}
              value={kpi.value}
              unit={kpi.unit}
              valueColor={kpi.isStatus ? statusColor : undefined}
            />
          ))}
        </div>

        {/* Frequency shift banner */}
        {comparisonStats &&
          (() => {
            const isNominal = shmStatus?.status === 'nominal'
            const shiftColor = isNominal
              ? 'text-[var(--dash-text)]'
              : comparisonStats.diff > 0
                ? 'text-green-400'
                : comparisonStats.diff < 0
                  ? 'text-red-400'
                  : 'text-[var(--dash-text)]'
            const pctColor = isNominal
              ? 'text-[var(--dash-text-muted)]'
              : comparisonStats.diff > 0
                ? 'text-green-500'
                : comparisonStats.diff < 0
                  ? 'text-red-500'
                  : 'text-[var(--dash-text-muted)]'
            return (
              <div className="flex items-center justify-between rounded-lg border border-[var(--dash-border)] bg-[var(--dash-surface-raised)] px-4 py-3">
                <div>
                  <span className={`text-cq-xl font-bold ${shiftColor}`}>
                    {comparisonStats.diff > 0 ? '+' : ''}
                    {(comparisonStats.diff * 1000).toFixed(2)} mHz
                  </span>
                  <div className="flex items-center gap-2 mt-0.5">
                    <span className={`text-cq-xs ${pctColor}`}>
                      ({comparisonStats.diffPercent > 0 ? '+' : ''}
                      {comparisonStats.diffPercent.toFixed(2)}%)
                    </span>
                    <span className="text-cq-2xs text-[var(--dash-text-muted)]">
                      {t('shm.comparison.vsPreviousPeriod')}
                    </span>
                  </div>
                </div>
                <div className="text-cq-2xs text-[var(--dash-text-muted)] uppercase tracking-wider">
                  {t('shm.comparison.freqShift')}
                </div>
              </div>
            )
          })()}

        <DetailSection title={t('shm.spectralHeatmap')}>
          <div className="rounded-lg bg-[var(--dash-surface-raised)] border border-[var(--dash-border)] p-2">
            {spectralLoading ? (
              <div className="h-[200px] rounded-lg bg-[var(--dash-surface-raised)] animate-pulse" />
            ) : spectralData ? (
              <SpectralHeatmapCanvas data={spectralData} />
            ) : (
              <div className="h-[200px] flex items-center justify-center text-cq-xs text-[var(--dash-text-muted)]">
                {t('shm.noSpectralData')}
              </div>
            )}
          </div>
        </DetailSection>

        <DetailSection title={t('shm.peakFrequencies')}>
          <div className="rounded-lg bg-[var(--dash-surface-raised)] border border-[var(--dash-border)] p-2">
            {peakLoading ? (
              <div className="h-[170px] rounded-lg bg-[var(--dash-surface-raised)] animate-pulse" />
            ) : peakData ? (
              <PeakScatterPlot data={peakData} />
            ) : (
              <div className="h-[170px] flex items-center justify-center text-cq-xs text-[var(--dash-text-muted)]">
                {t('shm.noPeakData')}
              </div>
            )}
          </div>
        </DetailSection>

        <div className="border-t border-[var(--dash-border)] pt-3">
          <ComparisonSection dataSummary={dataSummary} onStats={handleComparisonStats} />
        </div>
      </div>
    </div>
  )
}

export { StructureList, StructureDetail }
