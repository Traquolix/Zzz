/**
 * Tests for admin API client functions.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock client before importing
vi.mock('./client', () => ({
    apiRequest: vi.fn(),
    apiPaginatedRequest: vi.fn(),
}))

import { apiRequest, apiPaginatedRequest } from './client'
import {
    fetchUsers,
    createUser,
    updateUser,
    fetchOrganizations,
    createOrganization,
    fetchOrgSettings,
    updateOrgSettings,
    fetchFiberAssignments,
    createFiberAssignment,
    deleteFiberAssignment,
    fetchInfrastructure,
    deleteInfrastructure,
    fetchAlertRules,
    createAlertRule,
    deleteAlertRule,
    fetchAlertLogs,
} from './admin'

const mockApiRequest = vi.mocked(apiRequest)
const mockApiPaginatedRequest = vi.mocked(apiPaginatedRequest)

describe('Admin API - Users', () => {
    beforeEach(() => { vi.clearAllMocks() })

    it('fetchUsers calls GET /api/admin/users', async () => {
        mockApiPaginatedRequest.mockResolvedValue({
            results: [],
            hasMore: false,
            limit: 10,
            offset: 0,
            total: 0,
        })

        await fetchUsers()

        expect(mockApiPaginatedRequest).toHaveBeenCalledWith('/api/admin/users')
    })

    it('fetchUsers with search param appends query string', async () => {
        mockApiPaginatedRequest.mockResolvedValue({
            results: [],
            hasMore: false,
            limit: 10,
            offset: 0,
            total: 0,
        })

        await fetchUsers({ search: 'alice' })

        expect(mockApiPaginatedRequest).toHaveBeenCalledWith('/api/admin/users?search=alice')
    })

    it('fetchUsers with offset and limit appends query string', async () => {
        mockApiPaginatedRequest.mockResolvedValue({
            results: [],
            hasMore: false,
            limit: 10,
            offset: 10,
            total: 50,
        })

        await fetchUsers({ offset: 10, limit: 10 })

        expect(mockApiPaginatedRequest).toHaveBeenCalledWith('/api/admin/users?offset=10&limit=10')
    })

    it('createUser calls POST /api/admin/users with correct body', async () => {
        const mockUser = {
            id: 'user-001',
            username: 'testuser',
            email: 'test@example.com',
            role: 'user',
            isActive: true,
            organizationId: 'org-001',
            organizationName: 'Test Org',
        }

        mockApiRequest.mockResolvedValue(mockUser)

        const userData = {
            username: 'testuser',
            email: 'test@example.com',
            password: 'secure123',
            role: 'user',
        }

        const result = await createUser(userData)

        expect(mockApiRequest).toHaveBeenCalledWith('/api/admin/users', {
            method: 'POST',
            body: userData,
        })
        expect(result.id).toBe('user-001')
        expect(result.username).toBe('testuser')
    })
})

describe('Admin API - Organizations', () => {
    beforeEach(() => { vi.clearAllMocks() })

    it('fetchOrganizations calls GET /api/admin/organizations', async () => {
        mockApiPaginatedRequest.mockResolvedValue({
            results: [],
            hasMore: false,
            limit: 10,
            offset: 0,
            total: 0,
        })

        await fetchOrganizations()

        expect(mockApiPaginatedRequest).toHaveBeenCalledWith('/api/admin/organizations')
    })

    it('fetchOrganizations with search param appends query string', async () => {
        mockApiPaginatedRequest.mockResolvedValue({
            results: [],
            hasMore: false,
            limit: 10,
            offset: 0,
            total: 0,
        })

        await fetchOrganizations({ search: 'acme' })

        expect(mockApiPaginatedRequest).toHaveBeenCalledWith('/api/admin/organizations?search=acme')
    })

    it('createOrganization calls POST /api/admin/organizations with name', async () => {
        const mockOrg = {
            id: 'org-001',
            name: 'New Org',
            slug: 'new-org',
            isActive: true,
            createdAt: '2026-02-28T10:00:00Z',
        }

        mockApiRequest.mockResolvedValue(mockOrg)

        const result = await createOrganization('New Org')

        expect(mockApiRequest).toHaveBeenCalledWith('/api/admin/organizations', {
            method: 'POST',
            body: { name: 'New Org' },
        })
        expect(result.id).toBe('org-001')
        expect(result.name).toBe('New Org')
    })
})

describe('Admin API - Infrastructure', () => {
    beforeEach(() => { vi.clearAllMocks() })

    it('fetchInfrastructure calls GET /api/admin/infrastructure', async () => {
        mockApiPaginatedRequest.mockResolvedValue({
            results: [],
            hasMore: false,
            limit: 10,
            offset: 0,
            total: 0,
        })

        await fetchInfrastructure()

        expect(mockApiPaginatedRequest).toHaveBeenCalledWith('/api/admin/infrastructure')
    })

    it('fetchInfrastructure with search param appends query string', async () => {
        mockApiPaginatedRequest.mockResolvedValue({
            results: [],
            hasMore: false,
            limit: 10,
            offset: 0,
            total: 0,
        })

        await fetchInfrastructure({ search: 'bridge' })

        expect(mockApiPaginatedRequest).toHaveBeenCalledWith('/api/admin/infrastructure?search=bridge')
    })

    it('deleteInfrastructure calls DELETE /api/admin/infrastructure/:id', async () => {
        mockApiRequest.mockResolvedValue(null)

        await deleteInfrastructure('infra-001')

        expect(mockApiRequest).toHaveBeenCalledWith('/api/admin/infrastructure/infra-001', {
            method: 'DELETE',
        })
    })
})

describe('Admin API - Alert Rules', () => {
    beforeEach(() => { vi.clearAllMocks() })

    it('fetchAlertRules calls GET /api/admin/alert-rules', async () => {
        mockApiPaginatedRequest.mockResolvedValue({
            results: [],
            hasMore: false,
            limit: 10,
            offset: 0,
            total: 0,
        })

        await fetchAlertRules()

        expect(mockApiPaginatedRequest).toHaveBeenCalledWith('/api/admin/alert-rules')
    })

    it('fetchAlertRules with search param appends query string', async () => {
        mockApiPaginatedRequest.mockResolvedValue({
            results: [],
            hasMore: false,
            limit: 10,
            offset: 0,
            total: 0,
        })

        await fetchAlertRules({ search: 'speed' })

        expect(mockApiPaginatedRequest).toHaveBeenCalledWith('/api/admin/alert-rules?search=speed')
    })

    it('createAlertRule calls POST /api/admin/alert-rules', async () => {
        const mockRule = {
            id: 'rule-001',
            name: 'High Temperature Alert',
            ruleType: 'temperature',
            threshold: 85,
            isActive: true,
            dispatchChannel: 'email',
            organizationId: 'org-001',
        }

        mockApiRequest.mockResolvedValue(mockRule)

        const ruleData = {
            name: 'High Temperature Alert',
            ruleType: 'temperature',
            threshold: 85,
            dispatchChannel: 'email',
            organizationId: 'org-001',
        }

        const result = await createAlertRule(ruleData)

        expect(mockApiRequest).toHaveBeenCalledWith('/api/admin/alert-rules', {
            method: 'POST',
            body: ruleData,
        })
        expect(result.id).toBe('rule-001')
        expect(result.name).toBe('High Temperature Alert')
    })

    it('deleteAlertRule calls DELETE /api/admin/alert-rules/:id', async () => {
        mockApiRequest.mockResolvedValue(null)

        await deleteAlertRule('rule-001')

        expect(mockApiRequest).toHaveBeenCalledWith('/api/admin/alert-rules/rule-001', {
            method: 'DELETE',
        })
    })
})

// updateUser
describe('updateUser', () => {
    it('calls the correct endpoint with PATCH', async () => {
        const mockUser = { id: 'u1', username: 'test', role: 'operator', email: '', isActive: true, organizationId: null, organizationName: null, allowedWidgets: [], allowedLayers: [] }
        vi.mocked(apiRequest).mockResolvedValueOnce(mockUser)
        const result = await updateUser('u1', { role: 'operator' })
        expect(apiRequest).toHaveBeenCalledWith('/api/admin/users/u1', { method: 'PATCH', body: { role: 'operator' } })
        expect(result).toEqual(mockUser)
    })
})

// fetchOrgSettings
describe('fetchOrgSettings', () => {
    it('calls the correct endpoint', async () => {
        const mockSettings = { timezone: 'Europe/Paris', speedAlertThreshold: 20, incidentAutoResolveMinutes: 30, shmEnabled: true, allowedWidgets: [], allowedLayers: [] }
        vi.mocked(apiRequest).mockResolvedValueOnce(mockSettings)
        const result = await fetchOrgSettings('org-1')
        expect(apiRequest).toHaveBeenCalledWith('/api/admin/organizations/org-1/settings')
        expect(result).toEqual(mockSettings)
    })
})

// updateOrgSettings
describe('updateOrgSettings', () => {
    it('calls the correct endpoint with PATCH', async () => {
        const mockSettings = { timezone: 'UTC', speedAlertThreshold: 20, incidentAutoResolveMinutes: 30, shmEnabled: true, allowedWidgets: [], allowedLayers: [] }
        vi.mocked(apiRequest).mockResolvedValueOnce(mockSettings)
        await updateOrgSettings('org-1', { timezone: 'UTC' })
        expect(apiRequest).toHaveBeenCalledWith('/api/admin/organizations/org-1/settings', { method: 'PATCH', body: { timezone: 'UTC' } })
    })
})

// fetchFiberAssignments
describe('fetchFiberAssignments', () => {
    it('calls the correct endpoint', async () => {
        vi.mocked(apiRequest).mockResolvedValueOnce({ results: [] })
        await fetchFiberAssignments('org-1')
        expect(apiRequest).toHaveBeenCalledWith('/api/admin/organizations/org-1/fibers')
    })
})

// createFiberAssignment
describe('createFiberAssignment', () => {
    it('calls the correct endpoint with POST', async () => {
        const mockAssignment = { id: 'fa-1', fiberId: 'fiber-a', assignedAt: '2026-01-01T00:00:00Z' }
        vi.mocked(apiRequest).mockResolvedValueOnce(mockAssignment)
        await createFiberAssignment('org-1', 'fiber-a')
        expect(apiRequest).toHaveBeenCalledWith('/api/admin/organizations/org-1/fibers', { method: 'POST', body: { fiberId: 'fiber-a' } })
    })
})

// deleteFiberAssignment
describe('deleteFiberAssignment', () => {
    it('calls the correct endpoint with DELETE', async () => {
        vi.mocked(apiRequest).mockResolvedValueOnce(undefined)
        await deleteFiberAssignment('org-1', 'fa-1')
        expect(apiRequest).toHaveBeenCalledWith('/api/admin/organizations/org-1/fibers/fa-1', { method: 'DELETE' })
    })
})

// fetchAlertLogs
describe('fetchAlertLogs', () => {
    it('calls the correct endpoint', async () => {
        mockApiPaginatedRequest.mockResolvedValueOnce({
            results: [],
            hasMore: false,
            limit: 10,
            offset: 0,
            total: 0,
        })
        await fetchAlertLogs()
        expect(mockApiPaginatedRequest).toHaveBeenCalledWith('/api/admin/alert-logs')
    })

    it('fetchAlertLogs with search param appends query string', async () => {
        mockApiPaginatedRequest.mockResolvedValueOnce({
            results: [],
            hasMore: false,
            limit: 10,
            offset: 0,
            total: 0,
        })
        await fetchAlertLogs({ search: 'fiber' })
        expect(mockApiPaginatedRequest).toHaveBeenCalledWith('/api/admin/alert-logs?search=fiber')
    })
})
