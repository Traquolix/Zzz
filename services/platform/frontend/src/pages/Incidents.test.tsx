/**
 * Tests for the Incidents page - Responsive Split Panel
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'

// Mock the incidents hook
vi.mock('@/hooks/useIncidents', () => ({
    useIncidents: vi.fn(() => ({
        incidents: [
            {
                id: 'inc-1',
                fiberLine: 'Fiber-A1',
                type: 'slowdown',
                severity: 'high',
                channel: 'CH-01',
                detectedAt: '2024-03-01T10:00:00Z',
                status: 'investigating',
                duration: 3600000,
            },
        ],
        loading: false,
        isNewIncident: vi.fn(),
        updateIncidentStatus: vi.fn(),
    })),
}))

// Mock react-i18next
vi.mock('react-i18next', () => ({
    useTranslation: () => ({
        t: (key: string) => key,
        i18n: { language: 'en', changeLanguage: vi.fn() },
    }),
}))

// Mock the IncidentTimeline components
vi.mock('@/components/IncidentTimeline', () => ({
    IncidentTimeline: () => <div data-testid="incident-timeline">Timeline</div>,
    IncidentDetailPanel: ({ onClose }: any) => (
        <div data-testid="incident-detail-panel">
            <button onClick={onClose} data-testid="close-panel">Close</button>
            Detail Panel
        </div>
    ),
}))

// Mock other components
vi.mock('@/components/ui/SearchInput', () => ({
    SearchInput: () => <input data-testid="search-input" />,
}))

vi.mock('@/components/ui/EmptyState', () => ({
    EmptyState: () => <div data-testid="empty-state">Empty</div>,
}))

vi.mock('@/components/ui/Skeleton', () => ({
    Skeleton: () => <div data-testid="skeleton" />,
}))

vi.mock('@/lib/csvExport', () => ({
    downloadCSV: vi.fn(),
}))

import { Incidents } from './Incidents'

describe('Incidents Page - Responsive Split Panel', () => {
    beforeEach(() => {
        vi.clearAllMocks()
    })

    it('renders the incidents page', () => {
        render(<Incidents />)
        expect(screen.getByText('incidents.title')).toBeInTheDocument()
    })

    it('renders incident timeline', () => {
        render(<Incidents />)
        expect(screen.getByTestId('incident-timeline')).toBeInTheDocument()
    })

    it('detail panel has aria live region for announcements', () => {
        render(<Incidents />)
        const liveRegion = screen.getByRole('status')
        expect(liveRegion).toHaveAttribute('aria-live', 'polite')
        expect(liveRegion).toHaveClass('sr-only')
    })

})
