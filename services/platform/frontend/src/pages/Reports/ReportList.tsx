import { useTranslation } from 'react-i18next'
import { ScrollableTable } from '@/components/ui/ScrollableTable'
import { SearchInput } from "@/components/ui/SearchInput"
import { EmptyState } from "@/components/ui/EmptyState"
import { formatDate } from '@/lib/formatters'
import type { Report } from '@/types/report'

interface StatusBadgeProps {
    status: string
}

function StatusBadge({ status }: StatusBadgeProps) {
    const { t } = useTranslation()
    const classes: Record<string, string> = {
        pending: 'bg-yellow-100 text-yellow-800',
        generating: 'bg-blue-100 text-blue-800',
        completed: 'bg-green-100 text-green-800',
        failed: 'bg-red-100 text-red-800',
    }
    return (
        <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${classes[status] || 'bg-slate-100 text-slate-800'}`}>
            {t(`reports.statuses.${status}`)}
        </span>
    )
}

interface ReportListProps {
    reports: Report[]
    searchQuery: string
    onSearchChange: (query: string) => void
    onViewReport: (report: Report) => void
    onSendReport: (reportId: string, recipients: string[]) => void
}

export function ReportList({
    reports,
    searchQuery,
    onSearchChange,
    onViewReport,
    onSendReport,
}: ReportListProps) {
    const { t } = useTranslation()

    // Filter reports based on search query
    const filteredReports = (() => {
        if (!searchQuery.trim()) return reports

        const query = searchQuery.toLowerCase()
        return reports.filter(report =>
            report.title.toLowerCase().includes(query) ||
            report.status.toLowerCase().includes(query)
        )
    })()

    if (reports.length === 0) {
        return (
            <EmptyState
                title={t('reports.empty')}
                description={t('reports.emptyDescription')}
            />
        )
    }

    return (
        <>
            <div className="mb-6">
                <SearchInput
                    value={searchQuery}
                    onChange={onSearchChange}
                    placeholder={t('reports.searchPlaceholder', 'Search reports...')}
                />
            </div>

            {filteredReports.length === 0 ? (
                <EmptyState
                    title={t('reports.empty')}
                    description={t('reports.emptyDescription')}
                />
            ) : (
                <div className="bg-white dark:bg-slate-900 rounded-lg border border-slate-200 dark:border-slate-700 overflow-hidden">
                    <ScrollableTable>
                        <table className="w-full">
                            <thead>
                                <tr className="bg-slate-50 dark:bg-slate-800 text-left text-xs font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wider">
                                    <th className="px-4 py-3">{t('reports.titleLabel')}</th>
                                    <th className="px-4 py-3">{t('reports.dateRange')}</th>
                                    <th className="px-4 py-3">{t('reports.status')}</th>
                                    <th className="px-4 py-3">{t('reports.createdAt')}</th>
                                    <th className="px-4 py-3">{t('reports.actions')}</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                                {filteredReports.map((report) => (
                                    <tr key={report.id} className="hover:bg-slate-50 dark:hover:bg-slate-800">
                                        <td className="px-4 py-3 text-sm font-medium text-slate-700 dark:text-slate-300">
                                            {report.title}
                                        </td>
                                        <td className="px-4 py-3 text-sm text-slate-500 dark:text-slate-400">
                                            {formatDate(report.startTime)} - {formatDate(report.endTime)}
                                        </td>
                                        <td className="px-4 py-3">
                                            <StatusBadge status={report.status} />
                                        </td>
                                        <td className="px-4 py-3 text-sm text-slate-500 dark:text-slate-400">
                                            {formatDate(report.createdAt)}
                                        </td>
                                        <td className="px-4 py-3">
                                            <div className="flex items-center gap-2">
                                                {report.status === 'completed' && (
                                                    <>
                                                        <button
                                                            onClick={() => onViewReport(report)}
                                                            className="text-xs text-blue-600 hover:text-blue-800 font-medium"
                                                        >
                                                            {t('reports.view')}
                                                        </button>
                                                        <button
                                                            onClick={() => onSendReport(report.id, report.recipients)}
                                                            className="text-xs text-slate-500 hover:text-slate-700 font-medium"
                                                        >
                                                            {t('reports.send')}
                                                        </button>
                                                    </>
                                                )}
                                            </div>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </ScrollableTable>
                </div>
            )}
        </>
    )
}
