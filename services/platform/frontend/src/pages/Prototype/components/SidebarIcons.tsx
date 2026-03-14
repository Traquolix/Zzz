import { cn } from '@/lib/utils'
import { chartColors } from '../data'
import type { MetricKey } from '../types'

// ── Tab button ──────────────────────────────────────────────────────────

export function TabButton({
  label,
  icon,
  active,
  onClick,
  showDot,
}: {
  label: string
  icon: React.ReactNode
  active: boolean
  onClick: () => void
  showDot?: boolean
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        'relative flex flex-col items-center justify-center gap-1.5 w-[56px] py-3 rounded-l-lg border border-r-0 transition-colors cursor-pointer',
        active
          ? 'bg-[var(--proto-surface)] text-[var(--proto-text)] border-[var(--proto-border)]'
          : 'bg-[var(--proto-surface)]/60 text-[var(--proto-text-muted)] border-transparent hover:text-[var(--proto-text-secondary)] hover:bg-[var(--proto-surface)]/80',
      )}
    >
      {icon}
      <span className="text-[9px] font-medium leading-none">{label}</span>
      {showDot && <span className="absolute top-1.5 right-1.5 w-2 h-2 rounded-full bg-[var(--proto-red)]" />}
    </button>
  )
}

export const SidebarIcon = () => (
  <svg
    width="14"
    height="14"
    viewBox="0 0 14 14"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.3"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <rect x="1" y="2" width="12" height="10" rx="1.5" />
    <line x1="9" y1="2" x2="9" y2="12" />
    <rect x="9.5" y="4" width="2.5" height="6" rx="0.5" fill="currentColor" stroke="none" opacity="0.4" />
  </svg>
)

export const IncidentsIcon = () => (
  <svg
    width="20"
    height="20"
    viewBox="0 0 16 16"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.5"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <path d="M8 2L14 13H2L8 2Z" />
    <path d="M8 6.5V9" />
    <circle cx="8" cy="11" r="0.5" fill="currentColor" stroke="none" />
  </svg>
)

export const SectionsIcon = () => (
  <svg
    width="20"
    height="20"
    viewBox="0 0 16 16"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.5"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <path d="M2 4h12" />
    <path d="M2 8h12" />
    <path d="M2 12h12" />
    <circle cx="4" cy="4" r="1.5" fill="currentColor" stroke="none" />
    <circle cx="12" cy="8" r="1.5" fill="currentColor" stroke="none" />
    <circle cx="7" cy="12" r="1.5" fill="currentColor" stroke="none" />
  </svg>
)

export const MetricIcon = ({ metric }: { metric: MetricKey }) => {
  const color = chartColors[metric].color
  if (metric === 'speed')
    return (
      <svg
        width="14"
        height="14"
        viewBox="0 0 24 24"
        fill="none"
        stroke={color}
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d="M2 16a10 10 0 0 1 20 0" />
        <path d="M12 16l-3.5-6" />
        <circle cx="12" cy="16" r="1.5" fill={color} />
      </svg>
    )
  if (metric === 'flow')
    return (
      <svg
        width="14"
        height="14"
        viewBox="0 0 24 24"
        fill="none"
        stroke={color}
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <line x1="4" y1="5" x2="13" y2="5" />
        <polyline points="11,3 13,5 11,7" />
        <line x1="7" y1="12" x2="17" y2="12" />
        <polyline points="15,10 17,12 15,14" />
        <line x1="3" y1="19" x2="14" y2="19" />
        <polyline points="12,17 14,19 12,21" />
      </svg>
    )
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke={color}
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <rect x="4" y="3" width="16" height="18" rx="2" />
      <rect x="4" y="11" width="16" height="10" rx="0" fill={color} fillOpacity="0.35" stroke="none" />
    </svg>
  )
}

export const ExpandIcon = ({ expanded }: { expanded: boolean }) => (
  <svg
    width="12"
    height="12"
    className="group-hover/exp:scale-110 transition-transform"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    {expanded ? (
      <>
        <polyline points="13 17 18 12 13 7" />
        <polyline points="6 17 11 12 6 7" />
      </>
    ) : (
      <>
        <polyline points="11 17 6 12 11 7" />
        <polyline points="18 17 13 12 18 7" />
      </>
    )}
  </svg>
)

export const SettingsIcon = () => (
  <svg
    width="20"
    height="20"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.8"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z" />
    <circle cx="12" cy="12" r="3" />
  </svg>
)

export const BridgeIcon = () => (
  <svg
    width="20"
    height="20"
    viewBox="0 0 16 16"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.5"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <path d="M1 12h14" />
    <path d="M3 12V7" />
    <path d="M13 12V7" />
    <path d="M3 7C3 7 5.5 4 8 4C10.5 4 13 7 13 7" />
    <path d="M6 12V9" />
    <path d="M10 12V9" />
  </svg>
)

export const ChannelIcon = () => (
  <svg
    width="20"
    height="20"
    viewBox="0 0 16 16"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.5"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <circle cx="8" cy="8" r="3" />
    <line x1="8" y1="1" x2="8" y2="4" />
    <line x1="8" y1="12" x2="8" y2="15" />
    <line x1="1" y1="8" x2="4" y2="8" />
    <line x1="12" y1="8" x2="15" y2="8" />
  </svg>
)

export const DataHubIcon = () => (
  <svg
    width="20"
    height="20"
    viewBox="0 0 16 16"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.5"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <ellipse cx="8" cy="4" rx="6" ry="2" />
    <path d="M2 4v4c0 1.1 2.7 2 6 2s6-.9 6-2V4" />
    <path d="M2 8v4c0 1.1 2.7 2 6 2s6-.9 6-2V8" />
  </svg>
)

/* export const WaterfallIcon = () => (
    <svg width="20" height="20" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <rect x="2" y="2" width="12" height="12" rx="1" />
        <line x1="2" y1="6" x2="14" y2="6" opacity="0.3" />
        <line x1="2" y1="10" x2="14" y2="10" opacity="0.3" />
        <circle cx="5" cy="5" r="0.8" fill="currentColor" stroke="none" />
        <circle cx="8" cy="7" r="0.8" fill="currentColor" stroke="none" />
        <circle cx="11" cy="4" r="0.8" fill="currentColor" stroke="none" />
        <circle cx="6" cy="9" r="0.8" fill="currentColor" stroke="none" />
        <circle cx="10" cy="11" r="0.8" fill="currentColor" stroke="none" />
    </svg>
) */
