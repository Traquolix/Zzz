import { useTranslation } from 'react-i18next'
import { Modal } from '@/components/ui/modal'
import type { Report } from '@/types/report'

interface ReportDetailModalProps {
    report: Report
    onClose: () => void
}

export function ReportDetailModal({ report, onClose }: ReportDetailModalProps) {
    const { t } = useTranslation()

    return (
        <Modal open={true} onClose={onClose} className="max-w-4xl">
            <div className="flex flex-col max-h-[85vh]">
                <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200 dark:border-slate-700">
                    <h2 className="text-lg font-semibold text-slate-800 dark:text-slate-100">{report.title}</h2>
                    <button
                        onClick={onClose}
                        className="text-slate-400 dark:text-slate-500 hover:text-slate-600 dark:hover:text-slate-400 text-xl leading-none"
                    >
                        &times;
                    </button>
                </div>
                <div className="flex-1 overflow-auto p-1">
                    {report.htmlContent ? (
                        <iframe
                            srcDoc={report.htmlContent}
                            sandbox=""
                            title={t('reports.preview')}
                            className="w-full h-full min-h-[60vh] border-0"
                        />
                    ) : (
                        <div className="flex items-center justify-center h-64 text-slate-400">
                            {t('reports.noContent')}
                        </div>
                    )}
                </div>
            </div>
        </Modal>
    )
}
