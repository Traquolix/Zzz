import { useState, useEffect, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { showToast } from '@/lib/toast'
import { useFibers } from '@/hooks/useFibers'
import { fetchReports, generateReport, fetchReportDetail, sendReport, fetchSchedules, createSchedule, deleteSchedule } from '@/api/reports'
import { logger } from '@/lib/logger'
import { TableSkeleton } from '@/components/ui/Skeleton'
import { ReportForm } from './ReportForm'
import { ReportList } from './ReportList'
import { ScheduleListContent } from './ScheduleList'
import { ScheduleForm } from './ScheduleForm'
import { ReportDetailModal } from './ReportDetailModal'
import type { Report, GenerateReportRequest, ReportSchedule, CreateScheduleRequest } from '@/types/report'

export function Reports() {
    const { t } = useTranslation()
    const { fibers } = useFibers()

    // State management
    const [reports, setReports] = useState<Report[]>([])
    const [schedules, setSchedules] = useState<ReportSchedule[]>([])
    const [loading, setLoading] = useState(true)
    const [showForm, setShowForm] = useState(false)
    const [showScheduleForm, setShowScheduleForm] = useState(false)
    const [schedulesExpanded, setSchedulesExpanded] = useState(false)
    const [selectedReport, setSelectedReport] = useState<Report | null>(null)
    const [searchQuery, setSearchQuery] = useState("")
    const [generating, setGenerating] = useState(false)
    const [creatingSchedule, setCreatingSchedule] = useState(false)

    // Data loading
    const loadReports = useCallback(async () => {
        try {
            const response = await fetchReports()
            setReports(response.results)
        } catch (err) {
            showToast.error(t('common.error'))
            logger.error(err)
        } finally {
            setLoading(false)
        }
    }, [t])

    const loadSchedules = useCallback(async () => {
        try {
            const response = await fetchSchedules()
            setSchedules(response.results)
        } catch (err) {
            showToast.error(t('common.error'))
            logger.error(err)
        }
    }, [t])

    useEffect(() => {
        loadReports()
        loadSchedules()
    }, [loadReports, loadSchedules])

    // Event handlers
    const handleGenerate = async (data: GenerateReportRequest) => {
        setGenerating(true)
        try {
            const report = await generateReport(data)
            showToast.success(t('reports.generated'))
            setShowForm(false)
            setReports(prev => [report, ...prev])
        } catch (err) {
            showToast.error(t('common.error'))
            logger.error(err)
        } finally {
            setGenerating(false)
        }
    }

    const handleViewReport = async (report: Report) => {
        try {
            const detail = await fetchReportDetail(report.id)
            setSelectedReport(detail)
        } catch {
            showToast.error(t('common.error'))
        }
    }

    const handleSend = async (reportId: string, recipients: string[]) => {
        try {
            await sendReport(reportId, recipients)
            showToast.success(t('reports.sent'))
            loadReports()
        } catch {
            showToast.error(t('common.error'))
        }
    }

    const handleCreateSchedule = async (data: CreateScheduleRequest) => {
        setCreatingSchedule(true)
        try {
            const schedule = await createSchedule(data)
            showToast.success(t('reports.schedules.created'))
            setShowScheduleForm(false)
            setSchedules(prev => [schedule, ...prev])
        } catch (err) {
            showToast.error(t('common.error'))
            logger.error(err)
        } finally {
            setCreatingSchedule(false)
        }
    }

    const handleDeleteSchedule = async (scheduleId: string) => {
        try {
            await deleteSchedule(scheduleId)
            showToast.success(t('reports.schedules.deleted'))
            setSchedules(prev => prev.filter(s => s.id !== scheduleId))
        } catch (err) {
            showToast.error(t('common.error'))
            logger.error(err)
        }
    }

    if (loading) {
        return (
            <div className="h-full overflow-auto p-6">
                <div className="max-w-5xl mx-auto">
                    <div className="mb-8">
                        <div className="h-8 w-48 bg-slate-200 dark:bg-slate-700 rounded animate-pulse" />
                    </div>
                    <TableSkeleton rows={5} cols={5} />
                </div>
            </div>
        )
    }

    return (
        <div className="h-full overflow-auto p-6 bg-slate-50 dark:bg-slate-950">
            <div className="max-w-5xl mx-auto">
                {/* Header */}
                <div className="flex items-center justify-between mb-8">
                    <h1 className="text-2xl font-bold text-slate-800 dark:text-slate-100">{t('reports.title')}</h1>
                    <button
                        onClick={() => setShowForm(true)}
                        className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors"
                    >
                        {t('reports.generate')}
                    </button>
                </div>

                {/* Schedules Section */}
                <div className="mb-8">
                    <button
                        onClick={() => setSchedulesExpanded(!schedulesExpanded)}
                        className="flex items-center justify-between w-full px-4 py-3 bg-slate-50 dark:bg-slate-800 hover:bg-slate-100 dark:hover:bg-slate-700 border border-slate-200 dark:border-slate-700 rounded-lg transition-colors"
                    >
                        <h2 className="text-lg font-semibold text-slate-800 dark:text-slate-100">{t('reports.schedules.title')}</h2>
                        <span className="text-slate-400 dark:text-slate-500">
                            {schedulesExpanded ? '▼' : '▶'}
                        </span>
                    </button>

                    {schedulesExpanded && (
                        <ScheduleListContent
                            schedules={schedules}
                            onDeleteSchedule={handleDeleteSchedule}
                            onCreateClick={() => setShowScheduleForm(true)}
                        />
                    )}
                </div>

                {/* Reports List */}
                <ReportList
                    reports={reports}
                    searchQuery={searchQuery}
                    onSearchChange={setSearchQuery}
                    onViewReport={handleViewReport}
                    onSendReport={handleSend}
                />
            </div>

            {/* Modals */}
            {showForm && (
                <ReportForm
                    fibers={fibers}
                    generating={generating}
                    onGenerate={handleGenerate}
                    onClose={() => setShowForm(false)}
                />
            )}

            {showScheduleForm && (
                <ScheduleForm
                    fibers={fibers}
                    creating={creatingSchedule}
                    onCreate={handleCreateSchedule}
                    onClose={() => setShowScheduleForm(false)}
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
