import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'
import type { Infrastructure, SHMStatus } from '@/types/infrastructure'
import { StructureList, StructureDetail } from '../StructurePanels'
import { useStructureDetail } from '../../hooks/useStructureDetail'
import { useDashboard } from '../../context/DashboardContext'

interface ShmTabToolbarProps {
  shmSearch: string
  setShmSearch: (value: string) => void
  showStructuresOnMap: boolean
  showStructureLabels: boolean
}

export function ShmTabToolbar({
  shmSearch,
  setShmSearch,
  showStructuresOnMap,
  showStructureLabels,
}: ShmTabToolbarProps) {
  const { dispatch } = useDashboard()
  const { t } = useTranslation()

  return (
    <>
      <div className="relative">
        <svg
          className="absolute left-1.5 top-1/2 -translate-y-1/2 pointer-events-none text-[var(--dash-text-muted)]"
          width="12"
          height="12"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <circle cx="11" cy="11" r="8" />
          <line x1="21" y1="21" x2="16.65" y2="16.65" />
        </svg>
        <input
          type="text"
          value={shmSearch}
          onChange={e => setShmSearch(e.target.value)}
          placeholder={t('common.search')}
          className="w-28 focus:w-36 pl-5 pr-1.5 py-1 rounded bg-transparent border border-[var(--dash-border)] text-cq-xs text-[var(--dash-text)] placeholder:text-[var(--dash-text-muted)] outline-none focus:border-[var(--dash-text-secondary)] transition-all"
        />
      </div>
      <button
        onClick={() => dispatch({ type: 'TOGGLE_STRUCTURES_ON_MAP' })}
        className={cn(
          'flex items-center justify-center w-6 h-6 rounded transition-colors cursor-pointer',
          showStructuresOnMap
            ? 'text-[var(--dash-accent)]'
            : 'text-[var(--dash-text-muted)] hover:text-[var(--dash-text)]',
        )}
        title={t('sidebar.showOnMap')}
      >
        <svg
          width="14"
          height="14"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <rect x="1" y="5" width="22" height="14" rx="2" />
          <path d="M5 5v5" />
          <path d="M9 5v3" />
          <path d="M13 5v5" />
          <path d="M17 5v3" />
          <path d="M21 5v5" />
        </svg>
      </button>
      <button
        onClick={() => dispatch({ type: 'TOGGLE_STRUCTURE_LABELS' })}
        className={cn(
          'flex items-center justify-center w-6 h-6 rounded transition-colors cursor-pointer',
          showStructureLabels
            ? 'text-[var(--dash-accent)]'
            : 'text-[var(--dash-text-muted)] hover:text-[var(--dash-text)]',
        )}
        title={t('sidebar.showLabels')}
      >
        <svg
          width="14"
          height="14"
          viewBox="0 0 14 14"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <rect x="1" y="3" width="12" height="8" rx="1.5" />
          <path d="M4 7h6" />
          <path d="M4 9.5h3" />
        </svg>
      </button>
    </>
  )
}

interface ShmTabContentProps {
  structures: Infrastructure[]
  loading: boolean
  allStatuses: Map<string, SHMStatus>
  selectedStructureId: string | null
  onHighlightSection?: (sectionId: string) => void
  onClearHighlight?: () => void
  search: string
}

export function ShmTabContent({
  structures,
  loading,
  allStatuses,
  selectedStructureId,
  onHighlightSection,
  onClearHighlight,
  search,
}: ShmTabContentProps) {
  const { dispatch } = useDashboard()
  const detail = useStructureDetail(selectedStructureId, allStatuses)

  if (selectedStructureId) {
    return (
      <StructureDetail
        structure={structures.find(s => s.id === selectedStructureId) ?? null}
        shmStatus={detail.shmStatus}
        spectralData={detail.spectralData}
        spectralLoading={detail.spectralLoading}
        peakData={detail.peakData}
        peakLoading={detail.peakLoading}
        dataSummary={detail.dataSummary}
        onBack={() => dispatch({ type: 'CLEAR_SELECTION' })}
      />
    )
  }

  return (
    <StructureList
      structures={structures}
      loading={loading}
      allStatuses={allStatuses}
      search={search}
      onHighlightSection={onHighlightSection}
      onClearHighlight={onClearHighlight}
    />
  )
}
