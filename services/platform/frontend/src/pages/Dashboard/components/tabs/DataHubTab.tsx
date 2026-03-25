import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'
import { API_URL } from '@/constants/api'
import { DataHubPanel, type DataHubSubTab } from '../DataHubPanel'

interface DataHubTabToolbarProps {
  dataHubSubTab: DataHubSubTab
  showCreateKey: boolean
  setShowCreateKey: React.Dispatch<React.SetStateAction<boolean>>
  isAdmin: boolean
}

export function DataHubTabToolbar({ dataHubSubTab, showCreateKey, setShowCreateKey, isAdmin }: DataHubTabToolbarProps) {
  const { t } = useTranslation()

  return (
    <>
      {dataHubSubTab === 'apiKeys' && isAdmin && (
        <>
          <button
            onClick={() => setShowCreateKey(v => !v)}
            className={cn(
              'flex items-center justify-center w-6 h-6 rounded transition-colors cursor-pointer',
              showCreateKey
                ? 'text-[var(--dash-text)] bg-[var(--dash-surface-raised)]'
                : 'text-[var(--dash-text-muted)] hover:text-[var(--dash-text)]',
            )}
            title={t('apiKeys.createKey')}
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
              const curl = `curl -H "X-API-Key: YOUR_KEY" ${API_URL}/api/v1/fibers`
              navigator.clipboard.writeText(curl)
              toast.success(t('apiKeys.curlCopied'))
            }}
            className="flex items-center justify-center w-6 h-6 rounded text-[var(--dash-text-muted)] hover:text-[var(--dash-text-secondary)] transition-colors cursor-pointer"
            title={t('apiKeys.copyCurl')}
          >
            <svg
              width="12"
              height="12"
              viewBox="0 0 16 16"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M5 4L1 8l4 4M11 4l4 4-4 4" />
            </svg>
          </button>
        </>
      )}
      <a
        href={`${API_URL}/api/v1/docs/`}
        target="_blank"
        rel="noopener noreferrer"
        className="flex items-center justify-center w-6 h-6 rounded text-[var(--dash-text-muted)] hover:text-[var(--dash-text-secondary)] transition-colors cursor-pointer"
        title={t('userMenu.apiDocs')}
      >
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
      </a>
    </>
  )
}

interface DataHubTabContentProps {
  dataHubSubTab: DataHubSubTab
  isAdmin: boolean
  showCreateKey: boolean
  onCloseCreateKey: () => void
}

export function DataHubTabContent({ dataHubSubTab, isAdmin, showCreateKey, onCloseCreateKey }: DataHubTabContentProps) {
  return (
    <DataHubPanel
      subTab={dataHubSubTab}
      isAdmin={isAdmin}
      showCreateKey={showCreateKey}
      onCloseCreateKey={onCloseCreateKey}
    />
  )
}
