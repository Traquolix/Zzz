import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'

// Mock react-i18next
vi.mock('react-i18next', () => ({
    useTranslation: () => ({
        t: (key: string) => key,
        i18n: { language: 'en', changeLanguage: vi.fn() },
    }),
}))

// Mock hooks
vi.mock('@/hooks/useDashboard', () => ({
    useDashboard: vi.fn(() => ({
        editMode: false,
        toggleEditMode: vi.fn(),
        widgets: [{ id: 'widget-1', type: 'map' }],
        layouts: {},
        handleLayoutChange: vi.fn(),
        addWidget: vi.fn(),
        deleteWidget: vi.fn(),
        isLoading: false,
    })),
}))

// Mock components
vi.mock('@/components/Dashboard/DashboardHeader', () => ({
    DashboardHeader: ({ editMode }: any) => (
        <div data-testid="dashboard-header">{editMode ? 'Editing' : 'Viewing'}</div>
    ),
}))

vi.mock('@/components/Dashboard/DashboardGrid', () => ({
    DashboardGrid: () => <div data-testid="dashboard-grid">Grid</div>,
}))

vi.mock('@/components/Dashboard/Editing/EditTooltip', () => ({
    EditTooltip: ({ visible }: any) => (
        <div data-testid="edit-tooltip">{visible ? 'Visible' : 'Hidden'}</div>
    ),
}))

vi.mock('@/context/DashboardContext', () => ({
    DashboardProvider: ({ children }: any) => <div>{children}</div>,
}))

vi.mock('@/context/DashboardDataProvider', () => ({
    DashboardDataProvider: ({ children }: any) => <div>{children}</div>,
}))

vi.mock('@/components/ui/Skeleton', () => ({
    Skeleton: ({ className }: any) => (
        <div data-testid="skeleton" className={className} />
    ),
}))

vi.mock('@/components/ui/EmptyState', () => ({
    EmptyState: ({ title, description }: any) => (
        <div data-testid="empty-state">
            <h3>{title}</h3>
            <p>{description}</p>
        </div>
    ),
}))

import { Dashboard } from './Dashboard'

describe('Dashboard Page', () => {
    beforeEach(() => {
        vi.clearAllMocks()
    })

    it('renders dashboard grid', () => {
        render(<Dashboard />)
        expect(screen.getByTestId('dashboard-grid')).toBeInTheDocument()
    })

    it('renders dashboard header', () => {
        render(<Dashboard />)
        expect(screen.getByTestId('dashboard-header')).toBeInTheDocument()
    })

    it('renders edit tooltip', () => {
        render(<Dashboard />)
        expect(screen.getByTestId('edit-tooltip')).toBeInTheDocument()
    })

})
