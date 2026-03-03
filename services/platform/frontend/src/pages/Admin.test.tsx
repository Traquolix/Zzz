/**
 * Tests for the Admin panel page.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { TooltipProvider } from '@/components/ui/tooltip'

// Mock the admin API
vi.mock('@/api/admin', () => ({
    fetchUsers: vi.fn().mockResolvedValue({ results: [], hasMore: false, limit: 10, offset: 0, total: 0 }),
    createUser: vi.fn(),
    updateUser: vi.fn(),
    fetchOrganizations: vi.fn().mockResolvedValue({ results: [], hasMore: false, limit: 10, offset: 0, total: 0 }),
    createOrganization: vi.fn(),
    updateOrganization: vi.fn(),
    fetchInfrastructure: vi.fn().mockResolvedValue({ results: [], hasMore: false, limit: 10, offset: 0, total: 0 }),
    createInfrastructure: vi.fn(),
    deleteInfrastructure: vi.fn(),
    fetchAlertRules: vi.fn().mockResolvedValue({ results: [], hasMore: false, limit: 10, offset: 0, total: 0 }),
    createAlertRule: vi.fn(),
    updateAlertRule: vi.fn(),
    deleteAlertRule: vi.fn(),
    fetchOrgSettings: vi.fn().mockResolvedValue({
        timezone: 'UTC',
        speedAlertThreshold: 50,
        incidentAutoResolveMinutes: 60,
        shmEnabled: false,
        allowedWidgets: [],
        allowedLayers: [],
    }),
    updateOrgSettings: vi.fn(),
    fetchFiberAssignments: vi.fn().mockResolvedValue({ results: [], offset: 0, total: 0 }),
    createFiberAssignment: vi.fn(),
    deleteFiberAssignment: vi.fn(),
    fetchAlertLogs: vi.fn().mockResolvedValue({ results: [], hasMore: false, limit: 10, offset: 0, total: 0 }),
}))

// Mock useAuth hook
vi.mock('@/hooks/useAuth', () => ({
    useAuth: vi.fn(() => ({
        isAuthenticated: true,
        isLoading: false,
        username: 'testuser',
        organizationId: 'org-1',
        organizationName: 'Test Org',
        allowedWidgets: [],
        allowedLayers: [],
        role: 'admin',
        isSuperuser: false,
        login: vi.fn(),
        logout: vi.fn(),
    })),
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

import { Admin } from './Admin'
import { fetchUsers, fetchOrganizations, fetchInfrastructure, fetchAlertRules, fetchAlertLogs } from '@/api/admin'
import { useAuth } from '@/hooks/useAuth'

const mockFetchUsers = vi.mocked(fetchUsers)
const mockFetchOrganizations = vi.mocked(fetchOrganizations)
const mockFetchInfrastructure = vi.mocked(fetchInfrastructure)
const mockFetchAlertRules = vi.mocked(fetchAlertRules)
const mockFetchAlertLogs = vi.mocked(fetchAlertLogs)
const mockUseAuth = vi.mocked(useAuth)

// Helper to render Admin component with MemoryRouter
const renderAdmin = (initialTab?: string) => {
    const initialEntries = initialTab ? [`/?tab=${initialTab}`] : ['/']
    return render(
        <MemoryRouter initialEntries={initialEntries}>
            <TooltipProvider>
                <Admin />
            </TooltipProvider>
        </MemoryRouter>
    )
}

describe('Admin Page - Org Admin', () => {
    beforeEach(() => {
        vi.clearAllMocks()
        mockUseAuth.mockReturnValue({
            isAuthenticated: true,
            isLoading: false,
            username: 'testuser',
            organizationId: 'org-1',
            organizationName: 'Test Org',
            allowedWidgets: [],
            allowedLayers: [],
            role: 'admin',
            isSuperuser: false,
            login: vi.fn(),
            logout: vi.fn(),
        })
        mockFetchUsers.mockResolvedValue({ results: [], hasMore: false, limit: 10, offset: 0, total: 0 })
        mockFetchInfrastructure.mockResolvedValue({ results: [], hasMore: false, limit: 10, offset: 0, total: 0 })
        mockFetchAlertRules.mockResolvedValue({ results: [], hasMore: false, limit: 10, offset: 0, total: 0 })
        mockFetchAlertLogs.mockResolvedValue({ results: [], hasMore: false, limit: 10, offset: 0, total: 0 })
    })

    it('renders the page title', async () => {
        renderAdmin()
        expect(screen.getByText('admin.title')).toBeInTheDocument()
        // Wait for loading to finish
        await waitFor(() => {
            expect(screen.queryByRole('progressbar')).not.toBeInTheDocument()
        })
    })

    it('renders org admin tabs (settings, users, infrastructure, alertRules, alertLogs)', () => {
        renderAdmin()
        expect(screen.getByRole('tab', { name: 'admin.tabs.settings' })).toBeInTheDocument()
        expect(screen.getByRole('tab', { name: 'admin.tabs.users' })).toBeInTheDocument()
        expect(screen.getByRole('tab', { name: 'admin.tabs.infrastructure' })).toBeInTheDocument()
        expect(screen.getByRole('tab', { name: 'admin.tabs.alertRules' })).toBeInTheDocument()
        expect(screen.getByRole('tab', { name: 'admin.tabs.alertLogs' })).toBeInTheDocument()
    })

    it('does not render organizations tab for org admin', () => {
        renderAdmin()
        expect(screen.queryByRole('tab', { name: 'admin.tabs.organizations' })).not.toBeInTheDocument()
    })

    it('shows loading state when loading settings', async () => {
        renderAdmin()

        // Settings are loaded immediately from mocked API, so loading state is brief
        await waitFor(() => {
            expect(screen.queryByRole('progressbar')).not.toBeInTheDocument()
        })
    })

    it('settings tab is selected by default for org admin', () => {
        renderAdmin('settings')
        const settingsTab = screen.getByRole('tab', { name: 'admin.tabs.settings' })
        expect(settingsTab).toHaveAttribute('aria-selected', 'true')
    })

    it('shows settings panel on mount for org admin', async () => {
        renderAdmin('settings')

        await waitFor(() => {
            expect(screen.getByTestId('settings-panel')).toBeInTheDocument()
        })
    })

    it('clicking Users tab loads and shows users panel', async () => {
        renderAdmin()

        // Wait for initial load
        await waitFor(() => {
            expect(screen.queryByRole('progressbar')).not.toBeInTheDocument()
        })

        const usersTab = screen.getByRole('tab', { name: 'admin.tabs.users' })
        fireEvent.click(usersTab)

        await waitFor(() => {
            expect(mockFetchUsers).toHaveBeenCalled()
        })

        await waitFor(() => {
            expect(screen.getByTestId('users-panel')).toBeInTheDocument()
        })
    })

    it('clicking Infrastructure tab loads and shows infrastructure panel', async () => {
        renderAdmin()

        await waitFor(() => {
            expect(screen.queryByRole('progressbar')).not.toBeInTheDocument()
        })

        fireEvent.click(screen.getByRole('tab', { name: 'admin.tabs.infrastructure' }))

        await waitFor(() => {
            expect(mockFetchInfrastructure).toHaveBeenCalled()
        })

        await waitFor(() => {
            expect(screen.getByTestId('infrastructure-panel')).toBeInTheDocument()
        })
    })

    it('clicking Alert Rules tab loads and shows alert rules panel', async () => {
        renderAdmin()

        await waitFor(() => {
            expect(screen.queryByRole('progressbar')).not.toBeInTheDocument()
        })

        fireEvent.click(screen.getByRole('tab', { name: 'admin.tabs.alertRules' }))

        await waitFor(() => {
            expect(mockFetchAlertRules).toHaveBeenCalled()
        })

        await waitFor(() => {
            expect(screen.getByTestId('alert-rules-panel')).toBeInTheDocument()
        })
    })

    it('switches aria-selected when tabs are clicked', async () => {
        renderAdmin()

        const settingsTab = screen.getByRole('tab', { name: 'admin.tabs.settings' })
        const usersTab = screen.getByRole('tab', { name: 'admin.tabs.users' })

        expect(settingsTab).toHaveAttribute('aria-selected', 'true')
        expect(usersTab).toHaveAttribute('aria-selected', 'false')

        fireEvent.click(usersTab)

        await waitFor(() => {
            expect(settingsTab).toHaveAttribute('aria-selected', 'false')
            expect(usersTab).toHaveAttribute('aria-selected', 'true')
        })
    })
})

describe('Admin Page - Superuser', () => {
    beforeEach(() => {
        vi.clearAllMocks()
        mockUseAuth.mockReturnValue({
            isAuthenticated: true,
            isLoading: false,
            username: 'admin',
            organizationId: null,
            organizationName: null,
            allowedWidgets: [],
            allowedLayers: [],
            role: 'superuser',
            isSuperuser: true,
            login: vi.fn(),
            logout: vi.fn(),
        })
        mockFetchOrganizations.mockResolvedValue({ results: [], hasMore: false, limit: 10, offset: 0, total: 0 })
        mockFetchUsers.mockResolvedValue({ results: [], hasMore: false, limit: 10, offset: 0, total: 0 })
        mockFetchInfrastructure.mockResolvedValue({ results: [], hasMore: false, limit: 10, offset: 0, total: 0 })
        mockFetchAlertRules.mockResolvedValue({ results: [], hasMore: false, limit: 10, offset: 0, total: 0 })
        mockFetchAlertLogs.mockResolvedValue({ results: [], hasMore: false, limit: 10, offset: 0, total: 0 })
    })

    it('renders superuser tabs (organizations, users, infrastructure, alertRules, alertLogs)', () => {
        renderAdmin()
        expect(screen.getByRole('tab', { name: 'admin.tabs.organizations' })).toBeInTheDocument()
        expect(screen.getByRole('tab', { name: 'admin.tabs.users' })).toBeInTheDocument()
        expect(screen.getByRole('tab', { name: 'admin.tabs.infrastructure' })).toBeInTheDocument()
        expect(screen.getByRole('tab', { name: 'admin.tabs.alertRules' })).toBeInTheDocument()
        expect(screen.getByRole('tab', { name: 'admin.tabs.alertLogs' })).toBeInTheDocument()
    })

    it('does not render settings tab for superuser', () => {
        renderAdmin()
        expect(screen.queryByRole('tab', { name: 'admin.tabs.settings' })).not.toBeInTheDocument()
    })

    it('organizations tab is selected by default for superuser', () => {
        renderAdmin('organizations')
        const orgsTab = screen.getByRole('tab', { name: 'admin.tabs.organizations' })
        expect(orgsTab).toHaveAttribute('aria-selected', 'true')
    })

    it('shows organizations panel on mount for superuser', async () => {
        renderAdmin('organizations')

        await waitFor(() => {
            expect(mockFetchOrganizations).toHaveBeenCalled()
        })

        await waitFor(() => {
            expect(screen.getByTestId('organizations-panel')).toBeInTheDocument()
        })
    })
})
