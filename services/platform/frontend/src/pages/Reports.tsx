import { useState, useEffect, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { useFibers } from '@/hooks/useFibers'
import { fetchReports, generateReport, fetchReportDetail, sendReport } from '@/api/reports'
import type { Report, GenerateReportRequest } from '@/types/report'

const SECTION_OPTIONS = ['incidents', 'speed', 'volume'] as const

export function Reports() {
    const { t } = useTranslation()
    const { fibers } = useFibers()
    const [reports, setReports] = useState<Report[]>([])
    const [loading, setLoading] = useState(true)
    const [showForm, setShowForm] = useState(false)
    const [selectedReport, setSelectedReport] = useState<Report | null>(null)
    const [generating, setGenerating] = useState(false)

    const loadReports = useCallback(async () => {
        try {
            const data = await fetchReports()
            setReports(data)
        } catch (err) {
            toast.error(t('common.error'))
            console.error(err)
        } finally {
            setLoading(false)
        }
    }, [t])

    useEffect(() => { loadReports() }, [loadReports])

    const handleGenerate = async (data: GenerateReportRequest) => {
        setGenerating(true)
        try {
            const report = await generateReport(data)
            toast.success(t('reports.generated'))
            setShowForm(false)
            setReports(prev => [report, ...prev])
        } catch (err) {
            toast.error(t('common.error'))
            console.error(err)
        } finally {
            setGenerating(false)
        }
    }

    const handleViewReport = async (report: Report) => {
        try {
            const detail = await fetchReportDetail(report.id)
            setSelectedReport(detail)
        } catch {
            toast.error(t('common.error'))
        }
    }

    const handleSend = async (reportId: string, recipients: string[]) => {
        try {
            await sendReport(reportId, recipients)
            toast.success(t('reports.sent'))
            loadReports()
        } catch {
            toast.error(t('common.error'))
        }
    }

    if (loading) {
        return (
            <div className="flex items-center justify-center h-full text-slate-400">
                {t('common.loading')}
            </div>
        )
    }

    return (
        <div className="h-full overflow-auto p-6">
            <div className="max-w-5xl mx-auto">
                <div className="flex items-center justify-between mb-6">
                    <h1 className="text-2xl font-bold text-slate-800">{t('reports.title')}</h1>
                    <button
                        onClick={() => setShowForm(true)}
                        className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors"
                    >
                        {t('reports.generate')}
                    </button>
                </div>

                {reports.length === 0 ? (
                    <div className="text-center py-16 text-slate-400">
                        {t('reports.noReports')}
                    </div>
                ) : (
                    <div className="bg-white rounded-lg border border-slate-200 overflow-hidden">
                        <table className="w-full">
                            <thead>
                                <tr className="bg-slate-50 text-left text-xs font-medium text-slate-500 uppercase tracking-wider">
                                    <th className="px-4 py-3">{t('reports.titleLabel')}</th>
                                    <th className="px-4 py-3">{t('reports.dateRange')}</th>
                                    <th className="px-4 py-3">{t('reports.status')}</th>
                                    <th className="px-4 py-3">{t('reports.createdAt')}</th>
                                    <th className="px-4 py-3">{t('reports.actions')}</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-100">
                                {reports.map((report) => (
                                    <tr key={report.id} className="hover:bg-slate-50">
                                        <td className="px-4 py-3 text-sm font-medium text-slate-700">
                                            {report.title}
                                        </td>
                                        <td className="px-4 py-3 text-sm text-slate-500">
                                            {formatDate(report.startTime)} - {formatDate(report.endTime)}
                                        </td>
                                        <td className="px-4 py-3">
                                            <StatusBadge status={report.status} />
                                        </td>
                                        <td className="px-4 py-3 text-sm text-slate-500">
                                            {formatDate(report.createdAt)}
                                        </td>
                                        <td className="px-4 py-3">
                                            <div className="flex items-center gap-2">
                                                {report.status === 'completed' && (
                                                    <>
                                                        <button
                                                            onClick={() => handleViewReport(report)}
                                                            className="text-xs text-blue-600 hover:text-blue-800 font-medium"
                                                        >
                                                            {t('reports.view')}
                                                        </button>
                                                        <button
                                                            onClick={() => handleSend(report.id, report.recipients)}
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
                    </div>
                )}
            </div>

            {showForm && (
                <GenerateFormModal
                    fibers={fibers}
                    generating={generating}
                    onGenerate={handleGenerate}
                    onClose={() => setShowForm(false)}
                />
            )}

            {selectedReport && (
                <ReportDetailModal
                    report={selectedReport}
                    onClose={() => setSelectedReport(null)}
                />
            )}
        </div>
    )
}

function StatusBadge({ status }: { status: string }) {
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

function GenerateFormModal({
    fibers,
    generating,
    onGenerate,
    onClose,
}: {
    fibers: { id: string; name: string }[]
    generating: boolean
    onGenerate: (data: GenerateReportRequest) => void
    onClose: () => void
}) {
    const { t } = useTranslation()
    const [title, setTitle] = useState('')
    const [startTime, setStartTime] = useState('')
    const [endTime, setEndTime] = useState('')
    const [selectedFibers, setSelectedFibers] = useState<string[]>(fibers.map(f => f.id))
    const [selectedSections, setSelectedSections] = useState<string[]>([...SECTION_OPTIONS])
    const [recipientInput, setRecipientInput] = useState('')

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault()
        const recipients = recipientInput
            .split(',')
            .map(s => s.trim())
            .filter(Boolean)

        onGenerate({
            title,
            startTime: new Date(startTime).toISOString(),
            endTime: new Date(endTime).toISOString(),
            fiberIds: selectedFibers,
            sections: selectedSections,
            recipients,
        })
    }

    const toggleFiber = (id: string) => {
        setSelectedFibers(prev =>
            prev.includes(id) ? prev.filter(f => f !== id) : [...prev, id]
        )
    }

    const toggleSection = (section: string) => {
        setSelectedSections(prev =>
            prev.includes(section) ? prev.filter(s => s !== section) : [...prev, section]
        )
    }

    return (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50" onClick={onClose}>
            <div
                className="bg-white rounded-xl shadow-xl w-full max-w-lg mx-4 p-6"
                onClick={(e) => e.stopPropagation()}
            >
                <h2 className="text-lg font-semibold text-slate-800 mb-4">{t('reports.generateTitle')}</h2>
                <form onSubmit={handleSubmit} className="space-y-4">
                    <div>
                        <label className="block text-sm font-medium text-slate-700 mb-1">{t('reports.titleLabel')}</label>
                        <input
                            type="text"
                            value={title}
                            onChange={(e) => setTitle(e.target.value)}
                            required
                            className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                            placeholder={t('reports.titlePlaceholder')}
                        />
                    </div>

                    <div className="grid grid-cols-2 gap-3">
                        <div>
                            <label className="block text-sm font-medium text-slate-700 mb-1">{t('reports.startTime')}</label>
                            <input
                                type="datetime-local"
                                value={startTime}
                                onChange={(e) => setStartTime(e.target.value)}
                                required
                                className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                            />
                        </div>
                        <div>
                            <label className="block text-sm font-medium text-slate-700 mb-1">{t('reports.endTime')}</label>
                            <input
                                type="datetime-local"
                                value={endTime}
                                onChange={(e) => setEndTime(e.target.value)}
                                required
                                className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                            />
                        </div>
                    </div>

                    <div>
                        <label className="block text-sm font-medium text-slate-700 mb-1">{t('reports.fibers')}</label>
                        <div className="flex flex-wrap gap-2">
                            {fibers.map(fiber => (
                                <button
                                    key={fiber.id}
                                    type="button"
                                    onClick={() => toggleFiber(fiber.id)}
                                    className={`px-3 py-1 rounded-full text-xs font-medium border transition-colors ${
                                        selectedFibers.includes(fiber.id)
                                            ? 'bg-blue-100 border-blue-300 text-blue-700'
                                            : 'bg-white border-slate-200 text-slate-500'
                                    }`}
                                >
                                    {fiber.name || fiber.id}
                                </button>
                            ))}
                        </div>
                    </div>

                    <div>
                        <label className="block text-sm font-medium text-slate-700 mb-1">{t('reports.sections')}</label>
                        <div className="flex flex-wrap gap-2">
                            {SECTION_OPTIONS.map(section => (
                                <button
                                    key={section}
                                    type="button"
                                    onClick={() => toggleSection(section)}
                                    className={`px-3 py-1 rounded-full text-xs font-medium border transition-colors ${
                                        selectedSections.includes(section)
                                            ? 'bg-blue-100 border-blue-300 text-blue-700'
                                            : 'bg-white border-slate-200 text-slate-500'
                                    }`}
                                >
                                    {t(`reports.sectionLabels.${section}`)}
                                </button>
                            ))}
                        </div>
                    </div>

                    <div>
                        <label className="block text-sm font-medium text-slate-700 mb-1">{t('reports.recipients')}</label>
                        <input
                            type="text"
                            value={recipientInput}
                            onChange={(e) => setRecipientInput(e.target.value)}
                            className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                            placeholder={t('reports.recipientsPlaceholder')}
                        />
                    </div>

                    <div className="flex justify-end gap-3 pt-2">
                        <button
                            type="button"
                            onClick={onClose}
                            className="px-4 py-2 text-sm text-slate-600 hover:text-slate-800"
                        >
                            {t('common.cancel')}
                        </button>
                        <button
                            type="submit"
                            disabled={generating || !title || !startTime || !endTime || selectedFibers.length === 0 || selectedSections.length === 0}
                            className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                        >
                            {generating ? t('common.loading') : t('reports.generate')}
                        </button>
                    </div>
                </form>
            </div>
        </div>
    )
}

function ReportDetailModal({ report, onClose }: { report: Report; onClose: () => void }) {
    const { t } = useTranslation()

    return (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50" onClick={onClose}>
            <div
                className="bg-white rounded-xl shadow-xl w-full max-w-4xl mx-4 max-h-[85vh] flex flex-col"
                onClick={(e) => e.stopPropagation()}
            >
                <div className="flex items-center justify-between px-6 py-4 border-b">
                    <h2 className="text-lg font-semibold text-slate-800">{report.title}</h2>
                    <button
                        onClick={onClose}
                        className="text-slate-400 hover:text-slate-600 text-xl leading-none"
                    >
                        &times;
                    </button>
                </div>
                <div className="flex-1 overflow-auto p-1">
                    {report.htmlContent ? (
                        <iframe
                            srcDoc={report.htmlContent}
                            sandbox="allow-same-origin"
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
        </div>
    )
}

function formatDate(iso: string): string {
    if (!iso) return '-'
    return new Date(iso).toLocaleDateString(undefined, {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
    })
}
