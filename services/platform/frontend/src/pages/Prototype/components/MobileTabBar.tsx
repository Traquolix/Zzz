import { useState, useRef, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'
import type { ProtoAction, SidebarTab } from '../types'
import {
  MapIcon,
  SectionsIcon,
  IncidentsIcon,
  BridgeIcon,
  MoreIcon,
  SettingsIcon,
  DataHubIcon,
  ChannelIcon,
} from './SidebarIcons'

interface MobileTabBarProps {
  activeTab: SidebarTab
  sidebarOpen: boolean
  dispatch: React.Dispatch<ProtoAction>
  hasUnseen?: boolean
}

const primaryTabs = ['sections', 'incidents', 'shm'] as const
type PrimaryTab = (typeof primaryTabs)[number]

const secondaryTabs = ['settings', 'dataHub', 'channel', 'waterfall'] as const
type SecondaryTab = (typeof secondaryTabs)[number]

function isSecondaryTab(tab: SidebarTab): tab is SecondaryTab {
  return (secondaryTabs as readonly string[]).includes(tab)
}

const tabIcons: Record<PrimaryTab, React.ReactNode> = {
  sections: <SectionsIcon />,
  incidents: <IncidentsIcon />,
  shm: <BridgeIcon />,
}

const secondaryTabIcons: Record<SecondaryTab, React.ReactNode> = {
  settings: <SettingsIcon />,
  dataHub: <DataHubIcon />,
  channel: <ChannelIcon />,
  waterfall: <DataHubIcon />,
}

export function MobileTabBar({ activeTab, sidebarOpen, dispatch, hasUnseen }: MobileTabBarProps) {
  const { t } = useTranslation()
  const [moreOpen, setMoreOpen] = useState(false)
  const moreRef = useRef<HTMLDivElement>(null)

  // Close "More" popover on click outside
  useEffect(() => {
    if (!moreOpen) return
    const handler = (e: MouseEvent) => {
      if (moreRef.current && !moreRef.current.contains(e.target as Node)) {
        setMoreOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [moreOpen])

  const handleTabClick = (tab: SidebarTab) => {
    setMoreOpen(false)
    if (sidebarOpen && activeTab === tab) {
      // Re-tapping active tab closes panel
      dispatch({ type: 'TOGGLE_SIDEBAR' })
    } else {
      dispatch({ type: 'OPEN_PANEL', tab })
    }
  }

  const handleMapClick = () => {
    setMoreOpen(false)
    if (sidebarOpen) {
      dispatch({ type: 'TOGGLE_SIDEBAR' })
    }
  }

  const isMapActive = !sidebarOpen
  const isMoreActive = sidebarOpen && isSecondaryTab(activeTab)

  return (
    <nav
      className="fixed bottom-0 inset-x-0 z-40 md:hidden bg-[var(--proto-surface)] border-t border-[var(--proto-border)] proto-mobile-tabbar"
      aria-label="Main navigation"
    >
      <div className="flex h-14">
        {/* Map tab */}
        <button
          role="tab"
          aria-selected={isMapActive}
          onClick={handleMapClick}
          className={cn(
            'flex-1 flex flex-col items-center justify-center gap-0.5 text-[10px] font-medium transition-colors cursor-pointer',
            isMapActive ? 'text-[var(--proto-accent)]' : 'text-[var(--proto-text-muted)]',
          )}
        >
          <MapIcon />
          <span>{t('sidebar.mapTab')}</span>
        </button>

        {/* Primary tabs: Sections, Incidents, SHM */}
        {primaryTabs.map(tab => {
          const isActive = sidebarOpen && activeTab === tab
          return (
            <button
              key={tab}
              role="tab"
              aria-selected={isActive}
              onClick={() => handleTabClick(tab)}
              className={cn(
                'relative flex-1 flex flex-col items-center justify-center gap-0.5 text-[10px] font-medium transition-colors cursor-pointer',
                isActive ? 'text-[var(--proto-accent)]' : 'text-[var(--proto-text-muted)]',
              )}
            >
              {tabIcons[tab]}
              <span>
                {t(
                  tab === 'sections'
                    ? 'sidebar.sectionsTab'
                    : tab === 'incidents'
                      ? 'sidebar.incidentsTab'
                      : 'sidebar.shmTab',
                )}
              </span>
              {tab === 'incidents' && hasUnseen && (
                <span className="absolute top-2 right-1/2 translate-x-3.5 w-2 h-2 rounded-full bg-[var(--proto-red)]" />
              )}
            </button>
          )
        })}

        {/* More tab */}
        <div ref={moreRef} className="relative flex-1">
          <button
            role="tab"
            aria-selected={isMoreActive}
            onClick={() => setMoreOpen(v => !v)}
            className={cn(
              'w-full h-full flex flex-col items-center justify-center gap-0.5 text-[10px] font-medium transition-colors cursor-pointer',
              isMoreActive || moreOpen ? 'text-[var(--proto-accent)]' : 'text-[var(--proto-text-muted)]',
            )}
          >
            <MoreIcon />
            <span>{t('sidebar.moreTab')}</span>
          </button>

          {/* More popover */}
          {moreOpen && (
            <div className="absolute bottom-full mb-2 right-2 w-44 rounded-lg border border-[var(--proto-border)] bg-[var(--proto-surface)] shadow-xl overflow-hidden">
              <div className="py-1">
                <MoreMenuItem
                  icon={secondaryTabIcons.settings}
                  label={t('userMenu.settings')}
                  active={sidebarOpen && activeTab === 'settings'}
                  onClick={() => handleTabClick('settings')}
                />
                <MoreMenuItem
                  icon={secondaryTabIcons.dataHub}
                  label={t('userMenu.dataHub')}
                  active={sidebarOpen && activeTab === 'dataHub'}
                  onClick={() => handleTabClick('dataHub')}
                />
                <MoreMenuItem
                  icon={secondaryTabIcons.channel}
                  label="Channel"
                  active={sidebarOpen && activeTab === 'channel'}
                  onClick={() => handleTabClick('channel')}
                />
                <MoreMenuItem
                  icon={secondaryTabIcons.waterfall}
                  label="Waterfall"
                  active={sidebarOpen && activeTab === 'waterfall'}
                  onClick={() => handleTabClick('waterfall')}
                />
              </div>
            </div>
          )}
        </div>
      </div>
    </nav>
  )
}

function MoreMenuItem({
  icon,
  label,
  active,
  onClick,
}: {
  icon: React.ReactNode
  label: string
  active: boolean
  onClick: () => void
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        'w-full flex items-center gap-2.5 px-3 py-2 text-xs transition-colors cursor-pointer',
        active
          ? 'text-[var(--proto-accent)] bg-[var(--proto-accent)]/10'
          : 'text-[var(--proto-text-secondary)] hover:bg-[var(--proto-surface-raised)] hover:text-[var(--proto-text)]',
      )}
    >
      {icon}
      <span>{label}</span>
    </button>
  )
}
