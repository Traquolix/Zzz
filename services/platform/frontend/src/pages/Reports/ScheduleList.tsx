import { useTranslation } from 'react-i18next'
import { ScrollableTable } from '@/components/ui/ScrollableTable'
import { formatDate } from '@/lib/formatters'
import type { ReportSchedule } from '@/types/report'

interface ScheduleListContentProps {
    schedules: ReportSchedule[]
    onDeleteSchedule: (scheduleId: string) => void
    onCreateClick: () => void
}

export function ScheduleListContent({
    schedules,
    onDeleteSchedule,
    onCreateClick,
}: ScheduleListContentProps) {
    const { t } = useTranslation()

    return (
        <div className="mt-4">
            {schedules.length === 0 ? (
                <div className="text-center py-8 text-slate-400 dark:text-slate-500 bg-white dark:bg-slate-900 rounded-lg border border-slate-200 dark:border-slate-700">
                    {t('reports.schedules.noSchedules')}
                </div>
            ) : (
                <div className="bg-white dark:bg-slate-900 rounded-lg border border-slate-200 dark:border-slate-700 overflow-hidden">
                    <ScrollableTable>
                        <table className="w-full">
                            <thead>
                                <tr className="bg-slate-50 dark:bg-slate-800 text-left text-xs font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wider">
                                    <th className="px-4 py-3">{t('reports.titleLabel')}</th>
                                    <th className="px-4 py-3">{t('reports.schedules.frequency')}</th>
                                    <th className="px-4 py-3">{t('reports.schedules.fibers')}</th>
                                    <th className="px-4 py-3">{t('reports.schedules.sections')}</th>
                                    <th className="px-4 py-3">{t('reports.schedules.recipients')}</th>
                                    <th className="px-4 py-3">{t('reports.schedules.active')}</th>
                                    <th className="px-4 py-3">{t('reports.schedules.lastRun')}</th>
                                    <th className="px-4 py-3">{t('reports.actions')}</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                                {schedules.map((schedule) => (
                                    <tr key={schedule.id} className="hover:bg-slate-50 dark:hover:bg-slate-800">
                                        <td className="px-4 py-3 text-sm font-medium text-slate-700 dark:text-slate-300">
                                            {schedule.title}
                                        </td>
                                        <td className="px-4 py-3 text-sm text-slate-500 dark:text-slate-400">
                                            {t(`reports.schedules.${schedule.frequency}`)}
                                        </td>
                                        <td className="px-4 py-3 text-sm text-slate-500 dark:text-slate-400">
                                            {schedule.fiberIds.length}
                                        </td>
                                        <td className="px-4 py-3 text-sm text-slate-500 dark:text-slate-400">
                                            {schedule.sections.join(', ')}
                                        </td>
                                        <td className="px-4 py-3 text-sm text-slate-500 dark:text-slate-400">
                                            {schedule.recipients.length}
                                        </td>
                                        <td className="px-4 py-3">
                                            <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${
                                                schedule.isActive
                                                    ? 'bg-green-100 text-green-800'
                                                    : 'bg-slate-100 text-slate-600'
                                            }`}>
                                                {schedule.isActive ? t('common.yes') : t('common.no')}
                                            </span>
                                        </td>
                                        <td className="px-4 py-3 text-sm text-slate-500">
                                            {schedule.lastRunAt ? formatDate(schedule.lastRunAt) : '—'}
                                        </td>
                                        <td className="px-4 py-3">
                                            <button
                                                onClick={() => onDeleteSchedule(schedule.id)}
                                                className="text-xs text-red-600 hover:text-red-800 font-medium"
                                            >
                                                {t('common.delete')}
                                            </button>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </ScrollableTable>
                </div>
            )}
            <button
                onClick={onCreateClick}
                className="mt-4 px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors"
            >
                {t('reports.schedules.create')}
            </button>
        </div>
    )
}
