export type ReportStatus = 'pending' | 'generating' | 'completed' | 'failed'

export type Report = {
    id: string
    title: string
    status: ReportStatus
    startTime: string
    endTime: string
    fiberIds: string[]
    sections: string[]
    recipients: string[]
    sentAt: string | null
    createdAt: string
    createdBy: string | null
    htmlContent?: string
}

export type GenerateReportRequest = {
    title: string
    startTime: string
    endTime: string
    fiberIds: string[]
    sections: string[]
    recipients: string[]
}

export type ReportSchedule = {
    id: string
    title: string
    frequency: 'daily' | 'weekly' | 'monthly'
    fiberIds: string[]
    sections: string[]
    recipients: string[]
    isActive: boolean
    lastRunAt: string | null
    createdAt: string
}

export type CreateScheduleRequest = {
    title?: string
    frequency: 'daily' | 'weekly' | 'monthly'
    fiberIds: string[]
    sections: string[]
    recipients: string[]
}
