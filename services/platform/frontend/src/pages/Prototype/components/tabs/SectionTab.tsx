import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'
import { chartColors } from '@/lib/theme'
import type { MapPageAction, MetricKey, Section, LiveSectionStats, SectionDataPoint } from '../../types'
import { MAX_SECTIONS_PER_ORG } from '@/api/sections'
import { MetricIcon } from '../SidebarIcons'
import { SectionList, SectionDetail } from '../SectionPanels'

interface SectionTabToolbarProps {
  sectionSearch: string
  setSectionSearch: (value: string) => void
  sections: Section[]
  sectionMetric: MetricKey
  dispatch: React.Dispatch<MapPageAction>
}

export function SectionTabToolbar({
  sectionSearch,
  setSectionSearch,
  sections,
  sectionMetric,
  dispatch,
}: SectionTabToolbarProps) {
  const { t } = useTranslation()

  return (
    <>
      <div className="relative">
        <svg
          className="absolute left-1.5 top-1/2 -translate-y-1/2 pointer-events-none text-[var(--proto-text-muted)]"
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
          value={sectionSearch}
          onChange={e => setSectionSearch(e.target.value)}
          placeholder={t('common.search')}
          className="w-28 focus:w-36 pl-5 pr-1.5 py-1 rounded bg-transparent border border-[var(--proto-border)] text-cq-xs text-[var(--proto-text)] placeholder:text-[var(--proto-text-muted)] outline-none focus:border-[var(--proto-text-secondary)] transition-all"
        />
      </div>
      <button
        onClick={() => dispatch({ type: 'ENTER_SECTION_CREATION' })}
        disabled={sections.length >= MAX_SECTIONS_PER_ORG}
        className={cn(
          'flex items-center justify-center w-6 h-6 rounded transition-colors',
          sections.length >= MAX_SECTIONS_PER_ORG
            ? 'text-[var(--proto-text-muted)] opacity-40 cursor-not-allowed'
            : 'text-[var(--proto-text-muted)] hover:text-[var(--proto-text)] cursor-pointer',
        )}
        title={
          sections.length >= MAX_SECTIONS_PER_ORG
            ? t('sidebar.sectionLimitReached', { max: MAX_SECTIONS_PER_ORG })
            : t('sidebar.addSection')
        }
      >
        <svg
          width="14"
          height="14"
          viewBox="0 0 14 14"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
        >
          <line x1="7" y1="3" x2="7" y2="11" />
          <line x1="3" y1="7" x2="11" y2="7" />
        </svg>
      </button>
      <button
        onClick={() => {
          const keys = Object.keys(chartColors) as MetricKey[]
          const idx = keys.indexOf(sectionMetric)
          dispatch({ type: 'SET_SECTION_METRIC', metric: keys[(idx + 1) % keys.length] })
        }}
        className="flex items-center justify-center w-6 h-6 rounded hover:bg-[var(--proto-border)] transition-colors cursor-pointer"
        title={t(`sections.metric.${sectionMetric}`)}
      >
        <MetricIcon metric={sectionMetric} />
      </button>
    </>
  )
}

interface SectionTabContentProps {
  sections: Section[]
  selectedSectionId: string | null
  dispatch: React.Dispatch<MapPageAction>
  liveStats: Map<string, LiveSectionStats>
  liveSeriesData: Map<string, SectionDataPoint[]>
  sectionMetric: MetricKey
  fiberColors: Record<string, string>
  onHighlightSection?: (sectionId: string) => void
  onClearHighlight?: () => void
  search: string
}

export function SectionTabContent({
  sections,
  selectedSectionId,
  dispatch,
  liveStats,
  liveSeriesData,
  sectionMetric,
  fiberColors,
  onHighlightSection,
  onClearHighlight,
  search,
}: SectionTabContentProps) {
  const section = selectedSectionId ? sections.find(s => s.id === selectedSectionId) : null

  if (section) {
    return (
      <SectionDetail
        section={section}
        onBack={() => dispatch({ type: 'CLEAR_SELECTION' })}
        liveStats={liveStats}
        liveSeriesData={liveSeriesData}
        dispatch={dispatch}
        fiberColors={fiberColors}
      />
    )
  }

  return (
    <SectionList
      sections={sections}
      dispatch={dispatch}
      liveStats={liveStats}
      liveSeriesData={liveSeriesData}
      metric={sectionMetric}
      fiberColors={fiberColors}
      onHighlightSection={onHighlightSection}
      onClearHighlight={onClearHighlight}
      search={search}
    />
  )
}
