import { useState, useRef, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAuth } from '@/hooks/useAuth'
import { API_URL } from '@/constants/api'
import type { MapPageAction } from '../types'
import { SettingsIcon, DataHubIcon } from './SidebarIcons'

interface UserMenuProps {
  dispatch: React.Dispatch<MapPageAction>
}

export function UserMenu({ dispatch }: UserMenuProps) {
  const { username, role, isSuperuser, organizationName, logout } = useAuth()
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)

  const isAdmin = isSuperuser || role === 'admin'

  useEffect(() => {
    if (!open) return
    const handler = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  const handleLogout = useCallback(async () => {
    setOpen(false)
    await logout()
    navigate('/login')
  }, [logout, navigate])

  const openPanel = useCallback(
    (tab: 'settings' | 'dataHub') => {
      setOpen(false)
      dispatch({ type: 'OPEN_PANEL', tab })
    },
    [dispatch],
  )

  const initials = username
    ? username
        .split(/[\s._-]/)
        .filter(Boolean)
        .slice(0, 2)
        .map(s => s[0].toUpperCase())
        .join('')
    : '?'

  const roleBadge = isSuperuser
    ? t('userMenu.roleSuper')
    : role === 'admin'
      ? t('userMenu.roleAdmin')
      : role === 'viewer'
        ? t('userMenu.roleViewer')
        : role

  return (
    <div ref={menuRef} className="relative">
      <button
        onClick={() => setOpen(v => !v)}
        className="w-7 h-7 rounded-md bg-[var(--dash-base)] border border-[var(--dash-border)] text-[var(--dash-text-muted)] text-[10px] font-semibold flex items-center justify-center cursor-pointer hover:bg-[var(--dash-surface-raised)] hover:text-[var(--dash-text)] transition-colors"
        title={username ?? ''}
      >
        {initials}
      </button>

      {open && (
        <div className="absolute top-full mt-1.5 left-0 w-52 rounded-lg border border-[var(--dash-border)] bg-[var(--dash-surface)] shadow-xl overflow-hidden">
          {/* Profile — non-clickable */}
          <div className="px-3 py-2.5 border-b border-[var(--dash-border)]">
            <div className="flex items-center gap-2.5">
              <div className="w-6 h-6 rounded bg-[var(--dash-base)] border border-[var(--dash-border)] text-[var(--dash-text-muted)] text-[9px] font-semibold flex items-center justify-center shrink-0">
                {initials}
              </div>
              <div className="flex flex-col min-w-0">
                <div className="flex items-center gap-1.5">
                  <span className="text-xs font-medium text-[var(--dash-text)] truncate">{username}</span>
                  {roleBadge && (
                    <span className="text-[9px] px-1 py-px rounded bg-[var(--dash-accent)]/10 text-[var(--dash-accent)] font-medium">
                      {roleBadge}
                    </span>
                  )}
                </div>
                {organizationName && (
                  <span className="text-[10px] text-[var(--dash-text-muted)] truncate">{organizationName}</span>
                )}
              </div>
            </div>
          </div>

          {/* Menu items */}
          <div className="py-0.5">
            {isAdmin && (
              <div className="flex items-center">
                <button
                  onClick={() => openPanel('dataHub')}
                  className="flex-1 flex items-center gap-2.5 px-3 py-2 text-xs text-[var(--dash-text-secondary)] hover:bg-[var(--dash-surface-raised)] hover:text-[var(--dash-text)] transition-colors cursor-pointer"
                >
                  <DataHubIcon size={14} />
                  <span>{t('userMenu.dataHub')}</span>
                </button>
                <a
                  href={`${API_URL}/api/v1/docs/`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="shrink-0 flex items-center justify-center w-8 h-8 text-[var(--dash-text-muted)] hover:text-[var(--dash-text-secondary)] transition-colors cursor-pointer"
                  title={t('userMenu.apiDocs')}
                  onClick={() => setOpen(false)}
                >
                  <DocsIcon />
                </a>
              </div>
            )}
            <MenuItem
              icon={<SettingsIcon size={14} />}
              label={t('userMenu.settings')}
              onClick={() => openPanel('settings')}
            />
          </div>

          {/* Logout */}
          <div className="border-t border-[var(--dash-border)] py-0.5">
            <MenuItem icon={<LogoutIcon />} label={t('userMenu.logout')} onClick={handleLogout} danger />
          </div>
        </div>
      )}
    </div>
  )
}

function MenuItem({
  icon,
  label,
  onClick,
  danger,
}: {
  icon: React.ReactNode
  label: string
  onClick: () => void
  danger?: boolean
}) {
  return (
    <button
      onClick={onClick}
      className={`w-full flex items-center gap-2.5 px-3 py-2 text-xs transition-colors cursor-pointer ${
        danger
          ? 'text-red-400 hover:bg-red-500/10 hover:text-red-300'
          : 'text-[var(--dash-text-secondary)] hover:bg-[var(--dash-surface-raised)] hover:text-[var(--dash-text)]'
      }`}
    >
      {icon}
      <span>{label}</span>
    </button>
  )
}

// ── Icons ──────────────────────────────────────────────────────────

const DocsIcon = () => (
  <svg
    width="14"
    height="14"
    viewBox="0 0 16 16"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.5"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <path d="M4 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2z" />
    <path d="M5 5h6M5 8h6M5 11h3" />
  </svg>
)

const LogoutIcon = () => (
  <svg
    width="14"
    height="14"
    viewBox="0 0 16 16"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.5"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <path d="M6 14H3a1 1 0 0 1-1-1V3a1 1 0 0 1 1-1h3M11 11l3-3-3-3M5 8h9" />
  </svg>
)
