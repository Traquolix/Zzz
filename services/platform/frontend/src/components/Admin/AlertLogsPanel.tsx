import { useTranslation } from 'react-i18next'
import type { AlertLogEntry } from '@/types/admin'
import { EmptyState } from '@/components/ui/EmptyState'

export function AlertLogsPanel({ logs }: { logs: AlertLogEntry[] }) {
    const { t } = useTranslation()

    return (
        <div data-testid="alert-logs-panel">
            <h2 className="text-lg font-medium text-slate-700 mb-4">{t('admin.tabs.alertLogs')}</h2>
            {logs.length === 0 ? (
                <EmptyState
                    title={t('admin.noLogs')}
                    description={undefined}
                />
            ) : (
                <div className="bg-white rounded-lg border border-slate-200 overflow-hidden">
                    <table className="w-full">
                        <thead>
                            <tr className="bg-slate-50 text-left text-xs font-medium text-slate-500 uppercase tracking-wider">
                                <th className="px-4 py-3">{t('admin.settings.logs.ruleName')}</th>
                                <th className="px-4 py-3">{t('admin.settings.logs.fiber')}</th>
                                <th className="px-4 py-3">{t('admin.settings.logs.channel')}</th>
                                <th className="px-4 py-3">{t('admin.settings.logs.detail')}</th>
                                <th className="px-4 py-3">{t('admin.settings.logs.dispatchedAt')}</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100">
                            {logs.map(log => (
                                <tr key={log.id} className="hover:bg-slate-50">
                                    <td className="px-4 py-3 text-sm font-medium text-slate-700">{log.ruleName}</td>
                                    <td className="px-4 py-3 text-sm text-slate-500">{log.fiberId}</td>
                                    <td className="px-4 py-3 text-sm text-slate-500">{log.channel}</td>
                                    <td className="px-4 py-3 text-sm text-slate-500">{log.detail}</td>
                                    <td className="px-4 py-3 text-sm text-slate-500">
                                        {new Date(log.dispatchedAt).toLocaleString()}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}
        </div>
    )
}
