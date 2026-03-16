import { useRef, useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { useSidebarWidth } from '../hooks/useSidebarWidth'

interface LegendProps {
  displayMode: 'dots' | 'vehicles'
  onToggleDisplayMode: () => void
  isOverview?: boolean
  sidebarOpen?: boolean
  sidebarExpanded?: boolean
  hideFibersInOverview?: boolean
  onToggleHideFibers?: () => void
}

const TAB_BAR_OFFSET = 56 // 36px tab bar + 12px collapsed toggle gap + 8px spacing

export function Legend({
  displayMode,
  onToggleDisplayMode,
  isOverview,
  sidebarOpen,
  sidebarExpanded,
  hideFibersInOverview,
  onToggleHideFibers,
}: LegendProps) {
  const { t } = useTranslation()
  const sidebarWidth = useSidebarWidth()
  const right = sidebarOpen && sidebarWidth > 0 ? `${sidebarWidth + 12}px` : `${TAB_BAR_OFFSET}px`

  // Enable CSS transition only for sidebar open/close (transform-based slide).
  // During expand/collapse the sidebar width animates via CSS and ResizeObserver
  // tracks it at ~60fps — adding a transition on top would cause lag.
  const prevOpenRef = useRef(sidebarOpen)
  const [animating, setAnimating] = useState(false)
  if (prevOpenRef.current !== sidebarOpen) {
    prevOpenRef.current = sidebarOpen
    setAnimating(true)
  }
  useEffect(() => {
    if (!animating) return
    const id = setTimeout(() => setAnimating(false), sidebarExpanded ? 450 : 250)
    return () => clearTimeout(id)
  }, [animating, sidebarExpanded])

  return (
    <div
      className="absolute top-3 z-30 h-9 w-[120px] flex items-center rounded-lg
                        bg-[var(--proto-surface)]/90 border border-[var(--proto-border)]
                        backdrop-blur-sm pointer-events-auto overflow-hidden"
      style={{
        right,
        transition: animating ? `right ${sidebarExpanded ? '400ms' : '200ms'} ease-in-out` : 'none',
      }}
    >
      {isOverview ? (
        <div className="flex items-center justify-center gap-1.5 w-full">
          <button
            onClick={onToggleHideFibers}
            className="cursor-pointer flex items-center justify-center transition-colors"
            style={{ color: hideFibersInOverview ? 'var(--proto-text-muted)' : 'var(--proto-text)' }}
            title={hideFibersInOverview ? t('legend.showFibers') : t('legend.hideFibers')}
            aria-label={hideFibersInOverview ? t('legend.showFibers') : t('legend.hideFibers')}
          >
            {hideFibersInOverview ? <EyeOffIcon /> : <EyeIcon />}
          </button>
          <span className="text-[10px] font-medium uppercase tracking-wider text-[var(--proto-text)]">Overview</span>
        </div>
      ) : (
        <div className="flex items-center w-full h-full p-0.5 gap-0.5">
          <button
            onClick={() => displayMode !== 'dots' && onToggleDisplayMode()}
            className={`flex items-center justify-center gap-1 flex-1 h-full rounded text-[10px] font-medium uppercase tracking-wider transition-colors cursor-pointer ${
              displayMode === 'dots'
                ? 'bg-[var(--proto-surface-raised)] text-[var(--proto-text)]'
                : 'text-[var(--proto-text-muted)] hover:text-[var(--proto-text)]'
            }`}
          >
            <DotsIcon />
            Dots
          </button>
          <button
            onClick={() => displayMode !== 'vehicles' && onToggleDisplayMode()}
            className={`flex items-center justify-center gap-1 flex-1 h-full rounded text-[10px] font-medium uppercase tracking-wider transition-colors cursor-pointer ${
              displayMode === 'vehicles'
                ? 'bg-[var(--proto-surface-raised)] text-[var(--proto-text)]'
                : 'text-[var(--proto-text-muted)] hover:text-[var(--proto-text)]'
            }`}
          >
            <CubeIcon />
            3D
          </button>
        </div>
      )}
    </div>
  )
}

const DotsIcon = () => (
  <svg width="12" height="12" viewBox="0 0 16 16" fill="currentColor">
    <circle cx="4" cy="4" r="1.8" />
    <circle cx="11" cy="5" r="1.4" />
    <circle cx="7" cy="9" r="1.6" />
    <circle cx="12" cy="11" r="1.2" />
    <circle cx="4" cy="12" r="1.5" />
  </svg>
)

const CubeIcon = () => (
  <svg
    width="12"
    height="12"
    viewBox="0 0 16 16"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.2"
    strokeLinejoin="round"
  >
    <path d="M8 2L14 5.5V10.5L8 14L2 10.5V5.5L8 2Z" />
    <path d="M8 7.5L14 5.5" />
    <path d="M8 7.5L2 5.5" />
    <path d="M8 7.5V14" />
  </svg>
)

const EyeIcon = () => (
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
    <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
    <circle cx="12" cy="12" r="3" />
  </svg>
)

const EyeOffIcon = () => (
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
    <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94" />
    <path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19" />
    <line x1="1" y1="1" x2="23" y2="23" />
  </svg>
)
