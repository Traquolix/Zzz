import { useTranslation } from 'react-i18next'
import type { AdminAlertRule } from '@/types/admin'
import { ActiveBadge } from './shared'
import { EmptyState } from '@/components/ui/EmptyState'

export function AlertRulesPanel({
    rules,
    onCreateClick,
    onEditClick,
    onDelete,
}: {
    rules: AdminAlertRule[]
    onCreateClick: () => void
    onEditClick: (rule: AdminAlertRule) => void
    onDelete: (id: string) => void
}) {
    const { t } = useTranslation()

    return (
        <div data-testid="alert-rules-panel">
            <div className="flex items-center justify-between mb-4">
                <h2 className="text-lg font-medium text-slate-700 dark:text-slate-300">{t('admin.tabs.alertRules')}</h2>
                <button
                    onClick={onCreateClick}
                    className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors"
                >
                    {t('admin.createRule')}
                </button>
            </div>
            {rules.length === 0 ? (
                <EmptyState
                    title={t('admin.noRules')}
                    description={undefined}
                />
            ) : (
                <div className="bg-white dark:bg-slate-900 rounded-lg border border-slate-200 dark:border-slate-700 overflow-hidden">
                    <table className="w-full">
                        <thead>
                            <tr className="bg-slate-50 dark:bg-slate-800 text-left text-xs font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wider">
                                <th className="px-4 py-3">{t('common.name')}</th>
                                <th className="px-4 py-3">{t('admin.ruleType')}</th>
                                <th className="px-4 py-3">{t('admin.threshold')}</th>
                                <th className="px-4 py-3">{t('admin.dispatch')}</th>
                                <th className="px-4 py-3">{t('admin.status')}</th>
                                <th className="px-4 py-3">{t('reports.actions')}</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100 dark:divide-slate-700">
                            {rules.map(rule => (
                                <tr key={rule.id} className="hover:bg-slate-50 dark:hover:bg-slate-800/50">
                                    <td className="px-4 py-3 text-sm font-medium text-slate-700 dark:text-slate-200">{rule.name}</td>
                                    <td className="px-4 py-3 text-sm text-slate-500 dark:text-slate-400">{rule.ruleType}</td>
                                    <td className="px-4 py-3 text-sm text-slate-500 dark:text-slate-400">{rule.threshold ?? '—'}</td>
                                    <td className="px-4 py-3 text-sm text-slate-500 dark:text-slate-400">{rule.dispatchChannel}</td>
                                    <td className="px-4 py-3">
                                        <ActiveBadge isActive={rule.isActive} />
                                    </td>
                                    <td className="px-4 py-3">
                                        <div className="flex gap-3">
                                            <button
                                                onClick={() => onEditClick(rule)}
                                                className="text-xs text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300 font-medium"
                                            >
                                                {t('admin.edit')}
                                            </button>
                                            <button
                                                onClick={() => onDelete(rule.id)}
                                                className="text-xs text-red-600 hover:text-red-800 dark:text-red-400 dark:hover:text-red-300 font-medium"
                                            >
                                                {t('common.delete')}
                                            </button>
                                        </div>
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
