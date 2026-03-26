import { useState, useMemo } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { fibers } from '../data'
import { fetchExportEstimate, downloadExport, type ExportParams } from '@/api/export'

type DatePreset = '5m' | '1h' | '24h' | '7d' | '30d' | 'custom'
type DataType = 'detections' | 'incidents'
type Direction = 'both' | '0' | '1'
type Format = 'csv' | 'json'

// TTL thresholds (must match backend export_views.py)
const HIRES_HOURS = 48
const MEDIUM_DAYS = 90

// JSON is ~35% larger than CSV due to key repetition
const JSON_OVERHEAD = 1.35

function formatBytes(csvBytes: number, fmt: Format): string {
  const bytes = fmt === 'json' ? Math.round(csvBytes * JSON_OVERHEAD) : csvBytes
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`
}

function getPresetRange(preset: DatePreset): { start: string; end: string } | null {
  if (preset === 'custom') return null
  const end = new Date()
  const start = new Date()
  if (preset === '5m') start.setMinutes(start.getMinutes() - 5)
  else if (preset === '1h') start.setHours(start.getHours() - 1)
  else if (preset === '24h') start.setHours(start.getHours() - 24)
  else if (preset === '7d') start.setDate(start.getDate() - 7)
  else if (preset === '30d') start.setDate(start.getDate() - 30)
  return { start: start.toISOString(), end: end.toISOString() }
}

function getTierInfo(dateRange: { start: string; end: string } | null): {
  tier: 'hires' | '1m' | '1h'
  label: string
} | null {
  if (!dateRange) return null
  const now = Date.now()
  const startAge = now - new Date(dateRange.start).getTime()
  const startAgeHours = startAge / (1000 * 60 * 60)
  if (startAgeHours <= HIRES_HOURS) return { tier: 'hires', label: 'Raw' }
  if (startAgeHours <= MEDIUM_DAYS * 24) return { tier: '1m', label: '1 min' }
  return { tier: '1h', label: '1 hour' }
}

export function DataExportPanel() {
  const { t } = useTranslation()

  const uniqueCables = useMemo(() => {
    const seen = new Set<string>()
    return fibers.filter(f => {
      if (seen.has(f.parentCableId)) return false
      seen.add(f.parentCableId)
      return true
    })
  }, [])

  const [fiberId, setFiberId] = useState(uniqueCables[0]?.parentCableId ?? '')
  const [preset, setPreset] = useState<DatePreset>('24h')
  const [customStart, setCustomStart] = useState('')
  const [customEnd, setCustomEnd] = useState('')
  const [dataType, setDataType] = useState<DataType>('detections')
  const [direction, setDirection] = useState<Direction>('both')
  const [format, setFormat] = useState<Format>('csv')
  const [channelStart, setChannelStart] = useState('')
  const [channelEnd, setChannelEnd] = useState('')

  const dateRange = useMemo(() => {
    if (preset === 'custom') {
      if (!customStart || !customEnd) return null
      return { start: new Date(customStart).toISOString(), end: new Date(customEnd).toISOString() }
    }
    return getPresetRange(preset)
  }, [preset, customStart, customEnd])

  const tierInfo = useMemo(() => getTierInfo(dateRange), [dateRange])

  // Get max channels for the selected fiber
  const maxChannels = useMemo(() => {
    const fiber = fibers.find(f => f.parentCableId === fiberId)
    return fiber?.totalChannels ?? 0
  }, [fiberId])

  const parsedChStart = channelStart ? parseInt(channelStart, 10) : undefined
  const parsedChEnd = channelEnd ? parseInt(channelEnd, 10) : undefined

  const canEstimate = !!fiberId && !!dateRange

  const estimateQuery = useQuery({
    queryKey: [
      'export-estimate',
      fiberId,
      dateRange?.start,
      dateRange?.end,
      dataType,
      direction,
      parsedChStart,
      parsedChEnd,
    ],
    queryFn: () =>
      fetchExportEstimate({
        fiberId,
        start: dateRange!.start,
        end: dateRange!.end,
        type: dataType,
        direction: direction !== 'both' ? (Number(direction) as 0 | 1) : undefined,
        channelStart: parsedChStart,
        channelEnd: parsedChEnd,
      }),
    enabled: canEstimate,
    staleTime: 30_000,
  })

  const downloadMutation = useMutation({
    mutationFn: (params: ExportParams) => downloadExport(params),
    onSuccess: () => toast.success(t('export.downloadStarted')),
    onError: (err: Error) => toast.error(t(err.message)),
  })

  const handleDownload = () => {
    if (!dateRange || !fiberId) return
    downloadMutation.mutate({
      fiberId,
      start: dateRange.start,
      end: dateRange.end,
      type: dataType,
      direction: direction !== 'both' ? (Number(direction) as 0 | 1) : undefined,
      format,
      tier: estimateQuery.data?.tier ?? undefined,
      channelStart: parsedChStart,
      channelEnd: parsedChEnd,
    })
  }

  const estimateText = estimateQuery.isLoading
    ? '...'
    : estimateQuery.data
      ? t('export.estimatedSize', { size: formatBytes(estimateQuery.data.estimatedSize, format) })
      : null

  return (
    <div className="flex flex-col gap-3">
      {/* Fiber selector */}
      <FieldRow label={t('export.selectFiber')}>
        <select
          value={fiberId}
          onChange={e => setFiberId(e.target.value)}
          className="w-full px-2.5 py-1.5 rounded bg-[var(--dash-base)] border border-[var(--dash-border)] text-cq-xs text-[var(--dash-text)] outline-none truncate"
        >
          {uniqueCables.map(f => (
            <option key={f.parentCableId} value={f.parentCableId}>
              {f.name.replace(/ Dir \d$/, '')}
            </option>
          ))}
        </select>
      </FieldRow>

      {/* Date range */}
      <FieldRow label={t('export.dateRange')}>
        <ToggleGroup
          options={['5m', '1h', '24h', '7d', '30d', 'custom'] as DatePreset[]}
          value={preset}
          onChange={setPreset}
          labels={{
            '5m': t('export.preset_5m'),
            '1h': t('export.preset_1h'),
            '24h': t('export.preset_24h'),
            '7d': t('export.preset_7d'),
            '30d': t('export.preset_30d'),
            custom: t('export.preset_custom'),
          }}
        />
        {preset === 'custom' && (
          <div className="flex gap-1.5 mt-1.5">
            <input
              type="datetime-local"
              value={customStart}
              onChange={e => setCustomStart(e.target.value)}
              className="flex-1 px-2 py-1 rounded bg-[var(--dash-base)] border border-[var(--dash-border)] text-cq-xxs text-[var(--dash-text)] outline-none focus:border-[var(--dash-text-muted)]"
            />
            <input
              type="datetime-local"
              value={customEnd}
              onChange={e => setCustomEnd(e.target.value)}
              className="flex-1 px-2 py-1 rounded bg-[var(--dash-base)] border border-[var(--dash-border)] text-cq-xxs text-[var(--dash-text)] outline-none focus:border-[var(--dash-text-muted)]"
            />
          </div>
        )}
        {/* TTL tier info */}
        {tierInfo && dataType === 'detections' && (
          <span className="text-cq-xxs text-[var(--dash-text-muted)]/50 mt-0.5">
            {t('export.tierInfo', { tier: tierInfo.label })}
          </span>
        )}
      </FieldRow>

      {/* Data type */}
      <FieldRow label={t('export.dataType')}>
        <ToggleGroup
          options={['detections', 'incidents'] as DataType[]}
          value={dataType}
          onChange={setDataType}
          labels={{
            detections: t('export.type_detections'),
            incidents: t('export.type_incidents'),
          }}
        />
      </FieldRow>

      {/* Direction */}
      <FieldRow label={t('export.direction')}>
        <ToggleGroup
          options={['both', '0', '1'] as Direction[]}
          value={direction}
          onChange={setDirection}
          labels={{ both: t('export.dirBoth'), '0': 'D0', '1': 'D1' }}
        />
      </FieldRow>

      {/* Channel range */}
      <FieldRow label={t('export.channelRange')}>
        <div className="flex items-center gap-1.5">
          <input
            type="number"
            min={0}
            max={maxChannels || undefined}
            value={channelStart}
            onChange={e => setChannelStart(e.target.value)}
            placeholder="0"
            className="w-20 px-2 py-1 rounded bg-[var(--dash-base)] border border-[var(--dash-border)] text-cq-xxs text-[var(--dash-text)] placeholder:text-[var(--dash-text-muted)]/40 outline-none focus:border-[var(--dash-text-muted)] tabular-nums [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none"
          />
          <span className="text-cq-xxs text-[var(--dash-text-muted)]/40">—</span>
          <input
            type="number"
            min={0}
            max={maxChannels || undefined}
            value={channelEnd}
            onChange={e => setChannelEnd(e.target.value)}
            placeholder={maxChannels ? String(maxChannels) : ''}
            className="w-20 px-2 py-1 rounded bg-[var(--dash-base)] border border-[var(--dash-border)] text-cq-xxs text-[var(--dash-text)] placeholder:text-[var(--dash-text-muted)]/40 outline-none focus:border-[var(--dash-text-muted)] tabular-nums [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none"
          />
          {maxChannels > 0 && (
            <span className="text-cq-xxs text-[var(--dash-text-muted)]/40 tabular-nums">/ {maxChannels}</span>
          )}
        </div>
      </FieldRow>

      {/* Format */}
      <FieldRow label={t('export.format')}>
        <ToggleGroup
          options={['csv', 'json'] as Format[]}
          value={format}
          onChange={setFormat}
          labels={{ csv: 'CSV', json: 'JSON' }}
        />
      </FieldRow>

      {/* Estimate + Download */}
      <div className="flex items-center gap-2 pt-1">
        <button
          onClick={handleDownload}
          disabled={!canEstimate || downloadMutation.isPending}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded bg-[var(--dash-surface-raised)] border border-[var(--dash-border)] text-cq-xs font-medium text-[var(--dash-text)] disabled:opacity-30 cursor-pointer hover:bg-[var(--dash-border)] transition-colors"
        >
          {downloadMutation.isPending ? (
            <span className="inline-block w-3 h-3 border-[1.5px] border-[var(--dash-text-muted)] border-t-[var(--dash-text)] rounded-full animate-spin" />
          ) : (
            <DownloadIcon />
          )}
          {t('export.download')}
        </button>
        {canEstimate && estimateText && (
          <span className="text-cq-xxs text-[var(--dash-text-muted)]/50 tabular-nums">{estimateText}</span>
        )}
      </div>
    </div>
  )
}

// ── Field row ──────────────────────────────────────────────────────

function FieldRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5">
      <label className="text-cq-xxs text-[var(--dash-text-muted)]/60 uppercase tracking-wider">{label}</label>
      {children}
    </div>
  )
}

// ── Shared toggle group ──────────────────────────────────────────

function ToggleGroup<T extends string>({
  options,
  value,
  onChange,
  labels,
}: {
  options: T[]
  value: T
  onChange: (v: T) => void
  labels: Record<T, string>
}) {
  return (
    <div className="inline-flex rounded-md bg-[var(--dash-surface)] border border-[var(--dash-border)] p-0.5 gap-0.5">
      {options.map(opt => (
        <button
          key={opt}
          onClick={() => onChange(opt)}
          className={`px-2.5 py-1 rounded text-cq-xxs font-medium transition-colors cursor-pointer whitespace-nowrap ${
            value === opt
              ? 'bg-[var(--dash-surface-raised)] text-[var(--dash-text)]'
              : 'text-[var(--dash-text-secondary)] hover:text-[var(--dash-text)]'
          }`}
        >
          {labels[opt]}
        </button>
      ))}
    </div>
  )
}

// ── Icons ──────────────────────────────────────────────────────────

const DownloadIcon = () => (
  <svg
    width="12"
    height="12"
    viewBox="0 0 14 14"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.5"
    strokeLinecap="round"
  >
    <path d="M7 1.5v8M3.5 6L7 9.5 10.5 6" />
    <path d="M1.5 10.5v2h11v-2" />
  </svg>
)
