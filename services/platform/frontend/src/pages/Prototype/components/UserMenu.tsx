import { useState, useRef, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAuth } from '@/hooks/useAuth'
import { API_URL } from '@/constants/api'
import type { ProtoAction } from '../types'

interface UserMenuProps {
  dispatch: React.Dispatch<ProtoAction>
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

  const roleBadge = isSuperuser ? 'Super' : role === 'admin' ? 'Admin' : role === 'viewer' ? 'Viewer' : role

  return (
    <div ref={menuRef} className="relative">
      <button
        onClick={() => setOpen(v => !v)}
        className="w-7 h-7 rounded-md bg-[var(--proto-base)] border border-[var(--proto-border)] text-[var(--proto-text-muted)] text-[10px] font-semibold flex items-center justify-center cursor-pointer hover:bg-[var(--proto-surface-raised)] hover:text-[var(--proto-text)] transition-colors"
        title={username ?? ''}
      >
        {initials}
      </button>

      {open && (
        <div className="absolute top-full mt-1.5 left-0 w-52 rounded-lg border border-[var(--proto-border)] bg-[var(--proto-surface)] shadow-xl overflow-hidden">
          {/* Profile — non-clickable */}
          <div className="px-3 py-2.5 border-b border-[var(--proto-border)]">
            <div className="flex items-center gap-2.5">
              <div className="w-6 h-6 rounded bg-[var(--proto-base)] border border-[var(--proto-border)] text-[var(--proto-text-muted)] text-[9px] font-semibold flex items-center justify-center shrink-0">
                {initials}
              </div>
              <div className="flex flex-col min-w-0">
                <div className="flex items-center gap-1.5">
                  <span className="text-xs font-medium text-[var(--proto-text)] truncate">{username}</span>
                  {roleBadge && (
                    <span className="text-[9px] px-1 py-px rounded bg-[var(--proto-accent)]/10 text-[var(--proto-accent)] font-medium">
                      {roleBadge}
                    </span>
                  )}
                </div>
                {organizationName && (
                  <span className="text-[10px] text-[var(--proto-text-muted)] truncate">{organizationName}</span>
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
                  className="flex-1 flex items-center gap-2.5 px-3 py-2 text-xs text-[var(--proto-text-secondary)] hover:bg-[var(--proto-surface-raised)] hover:text-[var(--proto-text)] transition-colors cursor-pointer"
                >
                  <DataHubIcon />
                  <span>{t('userMenu.dataHub')}</span>
                </button>
                <a
                  href={`${API_URL}/api/v1/docs/`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="shrink-0 flex items-center justify-center w-8 h-8 text-[var(--proto-text-muted)] hover:text-[var(--proto-text-secondary)] transition-colors cursor-pointer"
                  title={t('userMenu.apiDocs')}
                  onClick={() => setOpen(false)}
                >
                  <DocsIcon />
                </a>
              </div>
            )}
            <MenuItem icon={<SettingsIcon />} label={t('userMenu.settings')} onClick={() => openPanel('settings')} />
          </div>

          {/* Logout */}
          <div className="border-t border-[var(--proto-border)] py-0.5">
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
          : 'text-[var(--proto-text-secondary)] hover:bg-[var(--proto-surface-raised)] hover:text-[var(--proto-text)]'
      }`}
    >
      {icon}
      <span>{label}</span>
    </button>
  )
}

// ── Icons ──────────────────────────────────────────────────────────

const SettingsIcon = () => (
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
    <path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z" />
    <circle cx="12" cy="12" r="3" />
  </svg>
)

const DataHubIcon = () => (
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
    <ellipse cx="8" cy="4" rx="6" ry="2" />
    <path d="M2 4v4c0 1.1 2.7 2 6 2s6-.9 6-2V4" />
    <path d="M2 8v4c0 1.1 2.7 2 6 2s6-.9 6-2V8" />
  </svg>
)

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
