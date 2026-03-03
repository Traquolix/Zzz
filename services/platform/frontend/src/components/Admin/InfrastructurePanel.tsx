import { useTranslation } from 'react-i18next'
import type { AdminInfrastructure } from '@/types/admin'
import { EmptyState } from '@/components/ui/EmptyState'

export function InfrastructurePanel({
    infrastructure,
    onCreateClick,
    onEditClick,
    onDelete,
}: {
    infrastructure: AdminInfrastructure[]
    onCreateClick: () => void
    onEditClick: (infra: AdminInfrastructure) => void
    onDelete: (id: string) => void
}) {
    const { t } = useTranslation()

    return (
        <div data-testid="infrastructure-panel">
            <div className="flex items-center justify-between mb-4">
                <h2 className="text-lg font-medium text-slate-700 dark:text-slate-300">{t('admin.tabs.infrastructure')}</h2>
                <button
                    onClick={onCreateClick}
                    className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors"
                >
                    {t('admin.createInfra')}
                </button>
            </div>
            {infrastructure.length === 0 ? (
                <EmptyState
                    title={t('admin.noInfra')}
                    description={undefined}
                />
            ) : (
                <div className="bg-white dark:bg-slate-900 rounded-lg border border-slate-200 dark:border-slate-700 overflow-hidden">
                    <table className="w-full">
                        <thead>
                            <tr className="bg-slate-50 dark:bg-slate-800 text-left text-xs font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wider">
                                <th className="px-4 py-3">{t('common.name')}</th>
                                <th className="px-4 py-3">{t('admin.type')}</th>
                                <th className="px-4 py-3">{t('common.fiber')}</th>
                                <th className="px-4 py-3">{t('admin.channels')}</th>
                                <th className="px-4 py-3">{t('reports.actions')}</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100 dark:divide-slate-700">
                            {infrastructure.map(item => (
                                <tr key={item.id} className="hover:bg-slate-50 dark:hover:bg-slate-800/50">
                                    <td className="px-4 py-3 text-sm font-medium text-slate-700 dark:text-slate-200">{item.name}</td>
                                    <td className="px-4 py-3 text-sm text-slate-500 dark:text-slate-400">{item.type}</td>
                                    <td className="px-4 py-3 text-sm text-slate-500 dark:text-slate-400">{item.fiberId}</td>
                                    <td className="px-4 py-3 text-sm text-slate-500 dark:text-slate-400">{item.startChannel}–{item.endChannel}</td>
                                    <td className="px-4 py-3">
                                        <div className="flex gap-3">
                                            <button
                                                onClick={() => onEditClick(item)}
                                                className="text-xs text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300 font-medium"
                                            >
                                                {t('admin.edit')}
                                            </button>
                                            <button
                                                onClick={() => onDelete(item.id)}
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
