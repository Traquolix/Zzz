import { apiRequest } from './client'
import type { Report, GenerateReportRequest } from '@/types/report'

export async function fetchReports(): Promise<Report[]> {
    return apiRequest<Report[]>('/api/reports')
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
