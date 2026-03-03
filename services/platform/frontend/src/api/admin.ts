import { apiRequest, apiPaginatedRequest, type PaginatedResponse } from './client'
import type {
    AdminUser,
    CreateUserRequest,
    UpdateUserRequest,
    AdminOrganization,
    OrgSettings,
    FiberAssignment,
    AdminInfrastructure,
    CreateInfrastructureRequest,
    AdminAlertRule,
    CreateAlertRuleRequest,
    AlertLogEntry,
} from '@/types/admin'

type ListParams = {
    search?: string
    offset?: number
    limit?: number
}

function buildQueryString(params: ListParams): string {
    const parts: string[] = []
    if (params.search) parts.push(`search=${encodeURIComponent(params.search)}`)
    if (params.offset !== undefined) parts.push(`offset=${params.offset}`)
    if (params.limit !== undefined) parts.push(`limit=${params.limit}`)
    return parts.length ? `?${parts.join('&')}` : ''
}

// Users
export async function fetchUsers(params?: ListParams): Promise<PaginatedResponse<AdminUser>> {
    const qs = buildQueryString(params || {})
    return apiPaginatedRequest<AdminUser>(`/api/admin/users${qs}`)
}

export async function createUser(data: CreateUserRequest): Promise<AdminUser> {
    return apiRequest<AdminUser>('/api/admin/users', { method: 'POST', body: data })
}

// Organizations
export async function fetchOrganizations(params?: ListParams): Promise<PaginatedResponse<AdminOrganization>> {
    const qs = buildQueryString(params || {})
    return apiPaginatedRequest<AdminOrganization>(`/api/admin/organizations${qs}`)
}

export async function createOrganization(name: string): Promise<AdminOrganization> {
    return apiRequest<AdminOrganization>('/api/admin/organizations', { method: 'POST', body: { name } })
}

export async function updateOrganization(id: string, data: { name?: string; isActive?: boolean }): Promise<AdminOrganization> {
    return apiRequest<AdminOrganization>(`/api/admin/organizations/${id}`, { method: 'PATCH', body: data })
}

// Infrastructure
export async function fetchInfrastructure(params?: ListParams): Promise<PaginatedResponse<AdminInfrastructure>> {
    const qs = buildQueryString(params || {})
    return apiPaginatedRequest<AdminInfrastructure>(`/api/admin/infrastructure${qs}`)
}

export async function createInfrastructure(data: CreateInfrastructureRequest): Promise<AdminInfrastructure> {
    return apiRequest<AdminInfrastructure>('/api/admin/infrastructure', { method: 'POST', body: data })
}

export async function updateInfrastructure(id: string, data: Partial<CreateInfrastructureRequest>): Promise<AdminInfrastructure> {
    return apiRequest<AdminInfrastructure>(`/api/admin/infrastructure/${id}`, { method: 'PATCH', body: data })
}

export async function deleteInfrastructure(id: string): Promise<void> {
    return apiRequest<void>(`/api/admin/infrastructure/${id}`, { method: 'DELETE' })
}

// Alert Rules
export async function fetchAlertRules(params?: ListParams): Promise<PaginatedResponse<AdminAlertRule>> {
    const qs = buildQueryString(params || {})
    return apiPaginatedRequest<AdminAlertRule>(`/api/admin/alert-rules${qs}`)
}

export async function createAlertRule(data: CreateAlertRuleRequest): Promise<AdminAlertRule> {
    return apiRequest<AdminAlertRule>('/api/admin/alert-rules', { method: 'POST', body: data })
}

export async function updateAlertRule(id: string, data: Partial<CreateAlertRuleRequest>): Promise<AdminAlertRule> {
    return apiRequest<AdminAlertRule>(`/api/admin/alert-rules/${id}`, { method: 'PATCH', body: data })
}

export async function deleteAlertRule(id: string): Promise<void> {
    return apiRequest<void>(`/api/admin/alert-rules/${id}`, { method: 'DELETE' })
}

// User detail
export async function updateUser(id: string, data: UpdateUserRequest): Promise<AdminUser> {
    return apiRequest<AdminUser>(`/api/admin/users/${id}`, { method: 'PATCH', body: data })
}

// Organization settings
export async function fetchOrgSettings(orgId: string): Promise<OrgSettings> {
    return apiRequest<OrgSettings>(`/api/admin/organizations/${orgId}/settings`)
}

export async function updateOrgSettings(orgId: string, data: Partial<OrgSettings>): Promise<OrgSettings> {
    return apiRequest<OrgSettings>(`/api/admin/organizations/${orgId}/settings`, { method: 'PATCH', body: data })
}

// Fiber assignments
export async function fetchFiberAssignments(orgId: string): Promise<{ results: FiberAssignment[] }> {
    return apiRequest<{ results: FiberAssignment[] }>(`/api/admin/organizations/${orgId}/fibers`)
}

export async function createFiberAssignment(orgId: string, fiberId: string): Promise<FiberAssignment> {
    return apiRequest<FiberAssignment>(`/api/admin/organizations/${orgId}/fibers`, { method: 'POST', body: { fiberId } })
}

export async function deleteFiberAssignment(orgId: string, assignmentId: string): Promise<void> {
    return apiRequest<void>(`/api/admin/organizations/${orgId}/fibers/${assignmentId}`, { method: 'DELETE' })
}

// Alert logs
export async function fetchAlertLogs(params?: ListParams): Promise<PaginatedResponse<AlertLogEntry>> {
    const qs = buildQueryString(params || {})
    return apiPaginatedRequest<AlertLogEntry>(`/api/admin/alert-logs${qs}`)
}
