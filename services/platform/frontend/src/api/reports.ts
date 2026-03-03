import { apiRequest, apiPaginatedRequest, type PaginatedResponse } from './client'
import type { Report, GenerateReportRequest, ReportSchedule, CreateScheduleRequest } from '@/types/report'

export async function fetchReports(): Promise<PaginatedResponse<Report>> {
    return apiPaginatedRequest<Report>('/api/reports')
}

export async function generateReport(data: GenerateReportRequest): Promise<Report> {
    return apiRequest<Report>('/api/reports/generate', {
        method: 'POST',
        body: data,
    })
}

export async function fetchReportDetail(reportId: string): Promise<Report> {
    return apiRequest<Report>(`/api/reports/${reportId}`)
}

export async function sendReport(reportId: string, recipients: string[]): Promise<{ sent: boolean }> {
    return apiRequest<{ sent: boolean }>(`/api/reports/${reportId}/send`, {
        method: 'POST',
        body: { recipients },
    })
}

export async function fetchSchedules(): Promise<PaginatedResponse<ReportSchedule>> {
    return apiPaginatedRequest<ReportSchedule>('/api/reports/schedules')
}

export async function createSchedule(data: CreateScheduleRequest): Promise<ReportSchedule> {
    return apiRequest<ReportSchedule>('/api/reports/schedules', {
        method: 'POST',
        body: data,
    })
}

export async function deleteSchedule(id: string): Promise<void> {
    return apiRequest<void>(`/api/reports/schedules/${id}`, {
        method: 'DELETE',
    })
}
