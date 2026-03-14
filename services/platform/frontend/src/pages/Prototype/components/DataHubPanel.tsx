import { useState, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { useAuth } from '@/hooks/useAuth'
import { DataExportPanel } from './DataExportPanel'
import { APIKeysPanel } from './APIKeysPanel'

export function DataHubPanel({ expanded }: { expanded: boolean }) {
  const { t } = useTranslation()
  const { isSuperuser, role } = useAuth()
  const isAdmin = isSuperuser || role === 'admin'
  const [subTab, setSubTab] = useState<'export' | 'apiKeys'>('export')

  const tabs = useMemo(() => {
    const list: { key: 'export' | 'apiKeys'; label: string }[] = [{ key: 'export', label: t('export.sectionTitle') }]
    if (isAdmin) list.push({ key: 'apiKeys', label: t('apiKeys.sectionTitle') })
    return list
  }, [isAdmin, t])

  return (
    <div className="flex flex-col h-full">
      {/* Underline tab nav */}
      {tabs.length > 1 && (
        <div className="flex items-center gap-4 px-4 border-b border-[var(--proto-border)]">
          {tabs.map(tab => (
            <button
              key={tab.key}
              onClick={() => setSubTab(tab.key)}
              className={`relative py-2.5 text-[length:var(--text-xs)] font-medium transition-colors cursor-pointer ${
                subTab === tab.key
                  ? 'text-[var(--proto-text)]'
                  : 'text-[var(--proto-text-muted)] hover:text-[var(--proto-text-secondary)]'
              }`}
            >
              {tab.label}
              {subTab === tab.key && (
                <span className="absolute bottom-0 left-0 right-0 h-[1.5px] bg-[var(--proto-text)]" />
              )}
            </button>
          ))}
        </div>
      )}

      {/* Tab content */}
      <div className="flex-1 overflow-y-auto px-4 py-3">
        {subTab === 'export' && <DataExportPanel expanded={expanded} />}
        {subTab === 'apiKeys' && isAdmin && <APIKeysPanel />}
      </div>
    </div>
  )
}

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
