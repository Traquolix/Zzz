/**
 * Tests for the Reports page including schedule management.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { TooltipProvider } from '@/components/ui/tooltip'

// Mock the reports API
vi.mock('@/api/reports', () => ({
    fetchReports: vi.fn().mockResolvedValue({ results: [], hasMore: false, limit: 50, offset: 0, total: 0 }),
    generateReport: vi.fn(),
    fetchReportDetail: vi.fn(),
    sendReport: vi.fn(),
    fetchSchedules: vi.fn().mockResolvedValue({ results: [], hasMore: false, limit: 50, offset: 0, total: 0 }),
    createSchedule: vi.fn(),
    deleteSchedule: vi.fn(),
}))

// Mock the fibers hook
vi.mock('@/hooks/useFibers', () => ({
    useFibers: () => ({
        fibers: [
            { id: 'carros', name: 'Carros' },
            { id: 'mathis', name: 'Mathis' },
        ],
    }),
}))

// Mock react-i18next
vi.mock('react-i18next', () => ({
    useTranslation: () => ({
        t: (key: string) => key,
        i18n: { language: 'en', changeLanguage: vi.fn() },
    }),
    initReactI18next: {
        type: '3rdParty',
        init: vi.fn(),
    },
}))

// Mock sonner
vi.mock('sonner', () => ({
    toast: { error: vi.fn(), success: vi.fn() },
}))

import { Reports } from './Reports'
import { fetchSchedules, createSchedule, deleteSchedule, fetchReports } from '@/api/reports'

const mockFetchSchedules = vi.mocked(fetchSchedules)
const mockCreateSchedule = vi.mocked(createSchedule)
const mockDeleteSchedule = vi.mocked(deleteSchedule)
const mockFetchReports = vi.mocked(fetchReports)

const waitForLoadingToFinish = async () => {
    await waitFor(() => {
        expect(screen.queryByText('common.loading')).not.toBeInTheDocument()
    }, { timeout: 3000 })
}

describe('Reports Page - Schedules', () => {
    beforeEach(() => {
        vi.clearAllMocks()
        mockFetchReports.mockResolvedValue({ results: [], hasMore: false, limit: 50, offset: 0, total: 0 })
        mockFetchSchedules.mockResolvedValue({ results: [], hasMore: false, limit: 50, offset: 0, total: 0 })
    })

    it('renders the schedules section', async () => {
        render(
            <TooltipProvider>
                <Reports />
            </TooltipProvider>
        )

        // Wait for loading to finish
        await waitForLoadingToFinish()

        // Check for schedules section header
        expect(screen.getByText('reports.schedules.title')).toBeInTheDocument()
    })

    it('shows "no schedules" message when empty', async () => {
        render(
            <TooltipProvider>
                <Reports />
            </TooltipProvider>
        )

        await waitForLoadingToFinish()

        // Click to expand schedules section
        const scheduleHeader = screen.getByText('reports.schedules.title').closest('button')
        fireEvent.click(scheduleHeader!)

        await waitFor(() => {
            expect(screen.getByText('reports.schedules.noSchedules')).toBeInTheDocument()
        })
    })

    it('opens create schedule modal when button is clicked', async () => {
        render(
            <TooltipProvider>
                <Reports />
            </TooltipProvider>
        )

        await waitForLoadingToFinish()

        // Expand schedules section
        const scheduleHeader = screen.getByText('reports.schedules.title').closest('button')
        fireEvent.click(scheduleHeader!)

        // Click create schedule button
        await waitFor(() => {
            const createButton = screen.getByText('reports.schedules.create')
            fireEvent.click(createButton)
        })

        // Check that modal is displayed with form elements
        await waitFor(() => {
            expect(screen.getByDisplayValue('reports.schedules.daily')).toBeInTheDocument()
        })
    })

    it('displays frequency selector in create modal', async () => {
        render(
            <TooltipProvider>
                <Reports />
            </TooltipProvider>
        )

        await waitForLoadingToFinish()

        // Expand and open modal
        const scheduleHeader = screen.getByText('reports.schedules.title').closest('button')
        fireEvent.click(scheduleHeader!)

        await waitFor(() => {
            const createButton = screen.getByText('reports.schedules.create')
            fireEvent.click(createButton)
        })

        const frequencySelect = screen.getByDisplayValue('reports.schedules.daily') as HTMLSelectElement
        expect(frequencySelect).toBeInTheDocument()
        expect(frequencySelect.value).toBe('daily')
    })

    it('displays fiber selection in create modal', async () => {
        render(
            <TooltipProvider>
                <Reports />
            </TooltipProvider>
        )

        await waitForLoadingToFinish()

        // Expand and open modal
        const scheduleHeader = screen.getByText('reports.schedules.title').closest('button')
        fireEvent.click(scheduleHeader!)

        await waitFor(() => {
            const createButton = screen.getByText('reports.schedules.create')
            fireEvent.click(createButton)
        })

        // Check for fiber buttons
        await waitFor(() => {
            expect(screen.getByText('Carros')).toBeInTheDocument()
            expect(screen.getByText('Mathis')).toBeInTheDocument()
        })
    })

    it('displays section checkboxes in create modal', async () => {
        render(
            <TooltipProvider>
                <Reports />
            </TooltipProvider>
        )

        await waitForLoadingToFinish()

        // Expand and open modal
        const scheduleHeader = screen.getByText('reports.schedules.title').closest('button')
        fireEvent.click(scheduleHeader!)

        await waitFor(() => {
            const createButton = screen.getByText('reports.schedules.create')
            fireEvent.click(createButton)
        })

        // Check for section labels
        await waitFor(() => {
            expect(screen.getByText('reports.sectionLabels.incidents')).toBeInTheDocument()
            expect(screen.getByText('reports.sectionLabels.speed')).toBeInTheDocument()
            expect(screen.getByText('reports.sectionLabels.volume')).toBeInTheDocument()
        })
    })

    it('displays recipient input in create modal', async () => {
        render(
            <TooltipProvider>
                <Reports />
            </TooltipProvider>
        )

        await waitForLoadingToFinish()

        // Expand and open modal
        const scheduleHeader = screen.getByText('reports.schedules.title').closest('button')
        fireEvent.click(scheduleHeader!)

        await waitFor(() => {
            const createButton = screen.getByText('reports.schedules.create')
            fireEvent.click(createButton)
        })

        const recipientInput = screen.getByPlaceholderText('reports.recipientsPlaceholder')
        expect(recipientInput).toBeInTheDocument()
    })

    it('creates schedule when form is submitted', async () => {
        const mockSchedule = {
            id: 'schedule-1',
            title: 'Daily Report',
            frequency: 'daily' as const,
            fiberIds: ['carros'],
            sections: ['incidents'],
            recipients: ['test@example.com'],
            isActive: true,
            lastRunAt: null,
            createdAt: '2026-02-28T00:00:00Z',
        }

        mockCreateSchedule.mockResolvedValue(mockSchedule)

        render(
            <TooltipProvider>
                <Reports />
            </TooltipProvider>
        )

        await waitForLoadingToFinish()

        // Expand and open modal
        const scheduleHeader = screen.getByText('reports.schedules.title').closest('button')
        fireEvent.click(scheduleHeader!)

        await waitFor(() => {
            const createButton = screen.getByText('reports.schedules.create')
            fireEvent.click(createButton)
        })

        // Fill form
        const recipientInput = screen.getByPlaceholderText('reports.recipientsPlaceholder') as HTMLInputElement
        fireEvent.change(recipientInput, { target: { value: 'test@example.com' } })

        // Submit form
        const submitButton = screen.getAllByText('reports.schedules.create').pop()
        fireEvent.click(submitButton!)

        await waitFor(() => {
            expect(mockCreateSchedule).toHaveBeenCalled()
        })
    })

    it('displays created schedule in table', async () => {
        const mockSchedule = {
            id: 'schedule-1',
            title: 'Daily Report',
            frequency: 'daily' as const,
            fiberIds: ['carros'],
            sections: ['incidents'],
            recipients: ['test@example.com'],
            isActive: true,
            lastRunAt: null,
            createdAt: '2026-02-28T00:00:00Z',
        }

        mockFetchSchedules.mockResolvedValue({
            results: [mockSchedule],
            hasMore: false,
            limit: 50,
            offset: 0,
            total: 1,
        })

        render(
            <TooltipProvider>
                <Reports />
            </TooltipProvider>
        )

        await waitForLoadingToFinish()

        // Expand schedules section
        const scheduleHeader = screen.getByText('reports.schedules.title').closest('button')
        fireEvent.click(scheduleHeader!)

        await waitFor(() => {
            expect(screen.getByText('Daily Report')).toBeInTheDocument()
        })
    })

    it('shows delete button for each schedule', async () => {
        const mockSchedule = {
            id: 'schedule-1',
            title: 'Daily Report',
            frequency: 'daily' as const,
            fiberIds: ['carros'],
            sections: ['incidents'],
            recipients: ['test@example.com'],
            isActive: true,
            lastRunAt: null,
            createdAt: '2026-02-28T00:00:00Z',
        }

        mockFetchSchedules.mockResolvedValue({
            results: [mockSchedule],
            hasMore: false,
            limit: 50,
            offset: 0,
            total: 1,
        })

        render(
            <TooltipProvider>
                <Reports />
            </TooltipProvider>
        )

        await waitForLoadingToFinish()

        // Expand schedules section
        const scheduleHeader = screen.getByText('reports.schedules.title').closest('button')
        fireEvent.click(scheduleHeader!)

        await waitFor(() => {
            const deleteButtons = screen.getAllByText('common.delete')
            expect(deleteButtons.length).toBeGreaterThan(0)
        })
    })

    it('deletes schedule when delete button is clicked', async () => {
        const mockSchedule = {
            id: 'schedule-1',
            title: 'Daily Report',
            frequency: 'daily' as const,
            fiberIds: ['carros'],
            sections: ['incidents'],
            recipients: ['test@example.com'],
            isActive: true,
            lastRunAt: null,
            createdAt: '2026-02-28T00:00:00Z',
        }

        mockFetchSchedules.mockResolvedValue({
            results: [mockSchedule],
            hasMore: false,
            limit: 50,
            offset: 0,
            total: 1,
        })

        mockDeleteSchedule.mockResolvedValue(undefined)

        render(
            <TooltipProvider>
                <Reports />
            </TooltipProvider>
        )

        await waitForLoadingToFinish()

        // Expand schedules section
        const scheduleHeader = screen.getByText('reports.schedules.title').closest('button')
        fireEvent.click(scheduleHeader!)

        await waitFor(() => {
            expect(screen.getByText('Daily Report')).toBeInTheDocument()
        })

        // Click delete button
        const deleteButton = screen.getByText('common.delete')
        fireEvent.click(deleteButton)

        await waitFor(() => {
            expect(mockDeleteSchedule).toHaveBeenCalledWith('schedule-1')
        })
    })

    it('toggles schedules section expansion', async () => {
        render(
            <TooltipProvider>
                <Reports />
            </TooltipProvider>
        )

        await waitForLoadingToFinish()

        const scheduleHeader = screen.getByText('reports.schedules.title').closest('button')

        // Initially collapsed
        expect(screen.queryByPlaceholderText('reports.recipientsPlaceholder')).not.toBeInTheDocument()

        // Expand
        fireEvent.click(scheduleHeader!)
        await waitFor(() => {
            expect(screen.getByText('reports.schedules.create')).toBeInTheDocument()
        })

        // Collapse
        fireEvent.click(scheduleHeader!)
        await waitFor(() => {
            expect(screen.queryByText('reports.schedules.create')).not.toBeInTheDocument()
        })
    })
})
