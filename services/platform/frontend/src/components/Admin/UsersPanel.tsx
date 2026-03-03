import { useTranslation } from 'react-i18next'
import type { AdminUser } from '@/types/admin'
import { ActiveBadge } from './shared'
import { EmptyState } from '@/components/ui/EmptyState'

export function UsersPanel({
    users,
    onCreateClick,
    onEditClick,
}: {
    users: AdminUser[]
    onCreateClick: () => void
    onEditClick: (user: AdminUser) => void
}) {
    const { t } = useTranslation()

    return (
        <div data-testid="users-panel">
            <div className="flex items-center justify-between mb-4">
                <h2 className="text-lg font-medium text-slate-700">{t('admin.tabs.users')}</h2>
                <button
                    onClick={onCreateClick}
                    className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors"
                >
                    {t('admin.createUser')}
                </button>
            </div>
            {users.length === 0 ? (
                <EmptyState
                    title={t('admin.noUsers')}
                    description={undefined}
                />
            ) : (
                <div className="bg-white rounded-lg border border-slate-200 overflow-hidden">
                    <table className="w-full">
                        <thead>
                            <tr className="bg-slate-50 text-left text-xs font-medium text-slate-500 uppercase tracking-wider">
                                <th className="px-4 py-3">{t('admin.username')}</th>
                                <th className="px-4 py-3">{t('admin.email')}</th>
                                <th className="px-4 py-3">{t('admin.role')}</th>
                                <th className="px-4 py-3">{t('admin.organization')}</th>
                                <th className="px-4 py-3">{t('admin.status')}</th>
                                <th className="px-4 py-3">{t('reports.actions')}</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100">
                            {users.map(user => (
                                <tr key={user.id} className="hover:bg-slate-50">
                                    <td className="px-4 py-3 text-sm font-medium text-slate-700">{user.username}</td>
                                    <td className="px-4 py-3 text-sm text-slate-500">{user.email || '—'}</td>
                                    <td className="px-4 py-3">
                                        <span className="inline-block px-2 py-0.5 rounded text-xs font-medium bg-slate-100 text-slate-700">
                                            {user.role}
                                        </span>
                                    </td>
                                    <td className="px-4 py-3 text-sm text-slate-500">{user.organizationName || '—'}</td>
                                    <td className="px-4 py-3">
                                        <ActiveBadge isActive={user.isActive} />
                                    </td>
                                    <td className="px-4 py-3">
                                        <button
                                            onClick={() => onEditClick(user)}
                                            className="text-xs text-blue-600 hover:text-blue-800 font-medium"
                                        >
                                            {t('admin.edit')}
                                        </button>
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
