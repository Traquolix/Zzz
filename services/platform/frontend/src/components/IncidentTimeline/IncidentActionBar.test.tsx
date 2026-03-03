import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { IncidentActionBar } from './IncidentActionBar'
import type { Incident } from '@/types/incident'
import { TooltipProvider } from '@/components/ui/tooltip'

vi.mock('@/api/incidents', () => ({
    postIncidentAction: vi.fn().mockResolvedValue({
        id: '1',
        fromStatus: 'active',
        toStatus: 'acknowledged',
        performedBy: null,
        note: '',
        performedAt: new Date().toISOString()
    }),
    fetchIncidentActions: vi.fn().mockResolvedValue({
        currentStatus: 'active',
        actions: []
    }),
}))

vi.mock('react-i18next', () => ({
    useTranslation: () => ({
        t: (key: string) => key
    }),
    initReactI18next: {
        type: '3rdParty',
        init: vi.fn(),
    },
}))

vi.mock('sonner', () => ({
    toast: {
        error: vi.fn(),
        success: vi.fn()
    },
}))

const mockIncident: Incident = {
    id: 'incident-1',
    type: 'accident',
    severity: 'critical',
    fiberLine: 'Fiber-A',
    channel: 5,
    detectedAt: new Date().toISOString(),
    status: 'active',
    duration: 1000,
}

describe('IncidentActionBar', () => {
    const mockOnStatusChange = vi.fn()

    beforeEach(() => {
        vi.clearAllMocks()
    })

    it('renders "Acknowledge" and "Investigate" and "Resolve" buttons when incident status is active', () => {
        render(
            <TooltipProvider>
                <IncidentActionBar
                    incident={mockIncident}
                    onStatusChange={mockOnStatusChange}
                />
            </TooltipProvider>
        )

        expect(screen.getByText('incidents.actions.acknowledged')).toBeInTheDocument()
        expect(screen.getByText('incidents.actions.investigating')).toBeInTheDocument()
        expect(screen.getByText('incidents.actions.resolved')).toBeInTheDocument()
    })

    it('renders "Investigate" and "Resolve" when status is acknowledged', () => {
        const acknowledgedIncident: Incident = {
            ...mockIncident,
            status: 'acknowledged',
        }

        render(
            <TooltipProvider>
                <IncidentActionBar
                    incident={acknowledgedIncident}
                    onStatusChange={mockOnStatusChange}
                />
            </TooltipProvider>
        )

        expect(screen.getByText('incidents.actions.investigating')).toBeInTheDocument()
        expect(screen.getByText('incidents.actions.resolved')).toBeInTheDocument()
        expect(screen.queryByText('incidents.actions.acknowledged')).not.toBeInTheDocument()
    })

    it('renders only "Resolve" when status is investigating', () => {
        const investigatingIncident: Incident = {
            ...mockIncident,
            status: 'investigating',
        }

        render(
            <TooltipProvider>
                <IncidentActionBar
                    incident={investigatingIncident}
                    onStatusChange={mockOnStatusChange}
                />
            </TooltipProvider>
        )

        expect(screen.getByText('incidents.actions.resolved')).toBeInTheDocument()
        expect(screen.queryByText('incidents.actions.acknowledged')).not.toBeInTheDocument()
        expect(screen.queryByText('incidents.actions.investigating')).not.toBeInTheDocument()
    })

    it('renders no buttons when status is resolved', () => {
        const resolvedIncident: Incident = {
            ...mockIncident,
            status: 'resolved',
        }

        render(
            <TooltipProvider>
                <IncidentActionBar
                    incident={resolvedIncident}
                    onStatusChange={mockOnStatusChange}
                />
            </TooltipProvider>
        )

        // Check that no action buttons are rendered
        expect(screen.queryByText('incidents.actions.acknowledged')).not.toBeInTheDocument()
        expect(screen.queryByText('incidents.actions.investigating')).not.toBeInTheDocument()
        expect(screen.queryByText('incidents.actions.resolved')).not.toBeInTheDocument()
    })

    it('calls postIncidentAction on button click', async () => {
        const { postIncidentAction } = await import('@/api/incidents')

        render(
            <TooltipProvider>
                <IncidentActionBar
                    incident={mockIncident}
                    onStatusChange={mockOnStatusChange}
                />
            </TooltipProvider>
        )

        const acknowledgeButton = screen.getByText('incidents.actions.acknowledged')
        fireEvent.click(acknowledgeButton)

        await waitFor(() => {
            expect(postIncidentAction).toHaveBeenCalledWith('incident-1', 'acknowledged', undefined)
        })
    })

    it('calls onStatusChange callback after successful action', async () => {
        render(
            <TooltipProvider>
                <IncidentActionBar
                    incident={mockIncident}
                    onStatusChange={mockOnStatusChange}
                />
            </TooltipProvider>
        )

        const acknowledgeButton = screen.getByText('incidents.actions.acknowledged')
        fireEvent.click(acknowledgeButton)

        await waitFor(() => {
            expect(mockOnStatusChange).toHaveBeenCalledWith('incident-1', 'acknowledged')
        })
    })

    it('disables buttons while submitting', async () => {
        const { postIncidentAction } = await import('@/api/incidents')
        vi.mocked(postIncidentAction).mockImplementationOnce(
            () => new Promise(resolve => setTimeout(resolve, 100))
        )

        render(
            <TooltipProvider>
                <IncidentActionBar
                    incident={mockIncident}
                    onStatusChange={mockOnStatusChange}
                />
            </TooltipProvider>
        )

        const acknowledgeButton = screen.getByText('incidents.actions.acknowledged') as HTMLButtonElement
        fireEvent.click(acknowledgeButton)

        // Button should be disabled immediately after click
        expect(acknowledgeButton.disabled).toBe(true)

        await waitFor(() => {
            expect(acknowledgeButton.disabled).toBe(false)
        })
    })
})
