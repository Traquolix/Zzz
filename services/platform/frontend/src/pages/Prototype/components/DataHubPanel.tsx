import { DataExportPanel } from './DataExportPanel'
import { APIKeysPanel } from './APIKeysPanel'

export type DataHubSubTab = 'export' | 'apiKeys'

export function DataHubPanel({
  subTab,
  isAdmin,
  showCreateKey,
  onCloseCreateKey,
}: {
  subTab: DataHubSubTab
  isAdmin: boolean
  showCreateKey: boolean
  onCloseCreateKey: () => void
}) {
  return (
    <div className="flex-1 overflow-y-auto px-4 py-3">
      {subTab === 'export' && <DataExportPanel />}
      {subTab === 'apiKeys' && isAdmin && <APIKeysPanel showCreate={showCreateKey} onCloseCreate={onCloseCreateKey} />}
    </div>
  )
}
