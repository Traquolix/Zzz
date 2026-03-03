import { useState, useEffect, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router-dom'
import { toast } from 'sonner'
import { useAuth } from '@/hooks/useAuth'
import {
    fetchUsers,
    createUser,
    updateUser,
    fetchOrganizations,
    createOrganization,
    updateOrganization,
    fetchInfrastructure,
    createInfrastructure,
    updateInfrastructure,
    deleteInfrastructure,
    fetchAlertRules,
    createAlertRule,
    updateAlertRule,
    deleteAlertRule,
    fetchAlertLogs,
} from '@/api/admin'
import type {
    AdminUser,
    AdminOrganization,
    AdminInfrastructure,
    AdminAlertRule,
    CreateUserRequest,
    CreateInfrastructureRequest,
    CreateAlertRuleRequest,
    UpdateUserRequest,
    AlertLogEntry,
} from '@/types/admin'
import { UsersPanel } from '@/components/Admin/UsersPanel'
import { SettingsPanel } from '@/components/Admin/SettingsPanel'
import { OrganizationsPanel } from '@/components/Admin/OrganizationsPanel'
import { InfrastructurePanel } from '@/components/Admin/InfrastructurePanel'
import { AlertRulesPanel } from '@/components/Admin/AlertRulesPanel'
import { AlertLogsPanel } from '@/components/Admin/AlertLogsPanel'
import { CreateUserModal, CreateOrgModal, CreateRuleModal, CreateInfraModal, EditUserModal, EditOrgModal, EditInfraModal, EditRuleModal } from '@/components/Admin/Modals'
import { SearchInput } from '@/components/ui/SearchInput'
import { TableSkeleton } from '@/components/ui/Skeleton'

type SuperuserTab = 'organizations' | 'users' | 'infrastructure' | 'alertRules' | 'alertLogs'
type OrgAdminTab = 'settings' | 'users' | 'infrastructure' | 'alertRules' | 'alertLogs'
type Tab = SuperuserTab | OrgAdminTab

const SUPERUSER_TABS: { key: SuperuserTab; labelKey: string }[] = [
    { key: 'organizations', labelKey: 'admin.tabs.organizations' },
    { key: 'users', labelKey: 'admin.tabs.users' },
    { key: 'infrastructure', labelKey: 'admin.tabs.infrastructure' },
    { key: 'alertRules', labelKey: 'admin.tabs.alertRules' },
    { key: 'alertLogs', labelKey: 'admin.tabs.alertLogs' },
]

const ORG_ADMIN_TABS: { key: OrgAdminTab; labelKey: string }[] = [
    { key: 'settings', labelKey: 'admin.tabs.settings' },
    { key: 'users', labelKey: 'admin.tabs.users' },
    { key: 'infrastructure', labelKey: 'admin.tabs.infrastructure' },
    { key: 'alertRules', labelKey: 'admin.tabs.alertRules' },
    { key: 'alertLogs', labelKey: 'admin.tabs.alertLogs' },
]

export function Admin() {
    const { t } = useTranslation()
    const auth = useAuth()
    const [searchParams, setSearchParams] = useSearchParams()

    const isSuperuser = auth.isSuperuser
    const tabs = isSuperuser ? SUPERUSER_TABS : ORG_ADMIN_TABS
    const defaultTab = isSuperuser ? 'organizations' : 'settings'

    // Read activeTab from URL search params, default to first tab for user role
    const activeTab = (searchParams.get('tab') || defaultTab) as Tab
    const [loading, setLoading] = useState(true)

    const [users, setUsers] = useState<AdminUser[]>([])
    const [organizations, setOrganizations] = useState<AdminOrganization[]>([])
    const [infrastructure, setInfrastructure] = useState<AdminInfrastructure[]>([])
    const [alertRules, setAlertRules] = useState<AdminAlertRule[]>([])
    const [alertLogs, setAlertLogs] = useState<AlertLogEntry[]>([])

    const [showCreateUser, setShowCreateUser] = useState(false)
    const [showCreateOrg, setShowCreateOrg] = useState(false)
    const [showCreateRule, setShowCreateRule] = useState(false)
    const [editingUser, setEditingUser] = useState<AdminUser | null>(null)
    const [editingOrg, setEditingOrg] = useState<AdminOrganization | null>(null)
    const [editingInfra, setEditingInfra] = useState<AdminInfrastructure | null>(null)
    const [editingRule, setEditingRule] = useState<AdminAlertRule | null>(null)
    const [showCreateInfra, setShowCreateInfra] = useState(false)
    const [searchQuery, setSearchQuery] = useState('')

    const loadTab = useCallback(async (tab: Tab, search?: string) => {
        setLoading(true)
        try {
            switch (tab) {
                case 'users': {
                    const res = await fetchUsers({ search })
                    setUsers(res.results)
                    break
                }
                case 'organizations': {
                    const res = await fetchOrganizations({ search })
                    setOrganizations(res.results)
                    break
                }
                case 'infrastructure': {
                    const res = await fetchInfrastructure({ search })
                    setInfrastructure(res.results)
                    break
                }
                case 'alertRules': {
                    const res = await fetchAlertRules({ search })
                    setAlertRules(res.results)
                    break
                }
                case 'alertLogs': {
                    const res = await fetchAlertLogs({ search })
                    setAlertLogs(res.results)
                    break
                }
                case 'settings': {
                    // Settings are loaded in SettingsPanel component itself
                    break
                }
            }
        } catch {
            toast.error(t('common.error'))
        } finally {
            setLoading(false)
        }
    }, [auth.organizationId, t])

    useEffect(() => {
        loadTab(activeTab)
    }, [activeTab, loadTab])

    // Debounced search effect
    useEffect(() => {
        const timer = setTimeout(() => {
            loadTab(activeTab, searchQuery)
        }, 300)
        return () => clearTimeout(timer)
    }, [searchQuery, activeTab, loadTab])

    const handleTabChange = (tab: Tab) => {
        setSearchParams({ tab }, { replace: true })
        setSearchQuery('')
    }

    const handleCreateUser = async (data: CreateUserRequest) => {
        try {
            const user = await createUser(data)
            setUsers(prev => [user, ...prev])
            setShowCreateUser(false)
            toast.success(t('admin.userCreated'))
        } catch {
            toast.error(t('common.error'))
        }
    }

    const handleUpdateUser = async (userId: string, data: UpdateUserRequest) => {
        try {
            const updated = await updateUser(userId, data)
            setUsers(prev => prev.map(u => u.id === userId ? updated : u))
            setEditingUser(null)
            toast.success(t('admin.userUpdated'))
        } catch {
            toast.error(t('common.error'))
        }
    }

    const handleCreateOrg = async (name: string) => {
        try {
            const org = await createOrganization(name)
            setOrganizations(prev => [org, ...prev])
            setShowCreateOrg(false)
            toast.success(t('admin.orgCreated'))
        } catch {
            toast.error(t('common.error'))
        }
    }

    const handleUpdateOrg = async (orgId: string, data: { name?: string; isActive?: boolean }) => {
        try {
            const updated = await updateOrganization(orgId, data)
            setOrganizations(prev => prev.map(o => o.id === orgId ? { ...o, ...updated } : o))
            setEditingOrg(null)
            toast.success(t('admin.orgUpdated'))
        } catch {
            toast.error(t('common.error'))
        }
    }

    const handleCreateRule = async (data: CreateAlertRuleRequest) => {
        try {
            const rule = await createAlertRule(data)
            setAlertRules(prev => [rule, ...prev])
            setShowCreateRule(false)
            toast.success(t('admin.ruleCreated'))
        } catch {
            toast.error(t('common.error'))
        }
    }

    const handleDeleteRule = async (id: string) => {
        try {
            await deleteAlertRule(id)
            setAlertRules(prev => prev.filter(r => r.id !== id))
            toast.success(t('admin.ruleDeleted'))
        } catch {
            toast.error(t('common.error'))
        }
    }

    const handleUpdateRule = async (id: string, data: Partial<CreateAlertRuleRequest>) => {
        try {
            const updated = await updateAlertRule(id, data)
            setAlertRules(prev => prev.map(r => r.id === id ? updated : r))
            setEditingRule(null)
            toast.success(t('admin.ruleUpdated'))
        } catch {
            toast.error(t('common.error'))
        }
    }

    const handleDeleteInfra = async (id: string) => {
        try {
            await deleteInfrastructure(id)
            setInfrastructure(prev => prev.filter(i => i.id !== id))
            toast.success(t('admin.infraDeleted'))
        } catch {
            toast.error(t('common.error'))
        }
    }

    const handleCreateInfra = async (data: CreateInfrastructureRequest) => {
        try {
            const infra = await createInfrastructure(data)
            setInfrastructure(prev => [infra, ...prev])
            setShowCreateInfra(false)
            toast.success(t('admin.infraCreated'))
        } catch {
            toast.error(t('common.error'))
        }
    }

    const handleUpdateInfra = async (id: string, data: Partial<CreateInfrastructureRequest>) => {
        try {
            const updated = await updateInfrastructure(id, data)
            setInfrastructure(prev => prev.map(i => i.id === id ? updated : i))
            setEditingInfra(null)
            toast.success(t('admin.infraUpdated'))
        } catch {
            toast.error(t('common.error'))
        }
    }

    return (
        <div className="h-full overflow-auto bg-slate-100 dark:bg-slate-950">
            <div className="max-w-6xl mx-auto p-6">
                <h1 className="text-2xl font-semibold text-slate-800 dark:text-slate-100 mb-6">{t('admin.title')}</h1>

                {/* Tabs */}
                <div className="flex border-b border-slate-200 dark:border-slate-700 mb-6" role="tablist">
                    {tabs.map(tab => (
                        <button
                            key={tab.key}
                            role="tab"
                            aria-selected={activeTab === tab.key}
                            onClick={() => handleTabChange(tab.key)}
                            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
                                activeTab === tab.key
                                    ? 'border-blue-600 text-blue-600'
                                    : 'border-transparent text-slate-500 hover:text-slate-700'
                            }`}
                        >
                            {t(tab.labelKey)}
                        </button>
                    ))}
                </div>

                {loading ? (
                    <div className="py-8" role="status">
                        <TableSkeleton rows={6} cols={5} />
                        <span className="sr-only">{t('common.loading')}</span>
                    </div>
                ) : (
                    <>
                        {activeTab !== 'settings' && (
                            <div className="mb-6">
                                <SearchInput
                                    value={searchQuery}
                                    onChange={setSearchQuery}
                                    placeholder={t('admin.searchPlaceholder', 'Search...')}
                                />
                            </div>
                        )}
                        {activeTab === 'users' && (
                            <UsersPanel
                                users={users}
                                onCreateClick={() => setShowCreateUser(true)}
                                onEditClick={setEditingUser}
                            />
                        )}
                        {activeTab === 'organizations' && isSuperuser && (
                            <OrganizationsPanel
                                organizations={organizations}
                                onCreateClick={() => setShowCreateOrg(true)}
                                onEditClick={setEditingOrg}
                            />
                        )}
                        {activeTab === 'settings' && !isSuperuser && (
                            <SettingsPanel organizationId={auth.organizationId || ''} />
                        )}
                        {activeTab === 'infrastructure' && (
                            <InfrastructurePanel
                                infrastructure={infrastructure}
                                onCreateClick={() => setShowCreateInfra(true)}
                                onEditClick={setEditingInfra}
                                onDelete={handleDeleteInfra}
                            />
                        )}
                        {activeTab === 'alertRules' && (
                            <AlertRulesPanel
                                rules={alertRules}
                                onCreateClick={() => setShowCreateRule(true)}
                                onEditClick={setEditingRule}
                                onDelete={handleDeleteRule}
                            />
                        )}
                        {activeTab === 'alertLogs' && (
                            <AlertLogsPanel logs={alertLogs} />
                        )}
                    </>
                )}
            </div>

            {showCreateUser && (
                <CreateUserModal
                    onSubmit={handleCreateUser}
                    onClose={() => setShowCreateUser(false)}
                />
            )}
            {showCreateOrg && (
                <CreateOrgModal
                    onSubmit={handleCreateOrg}
                    onClose={() => setShowCreateOrg(false)}
                />
            )}
            {showCreateRule && (
                <CreateRuleModal
                    onSubmit={handleCreateRule}
                    onClose={() => setShowCreateRule(false)}
                />
            )}
            {editingUser && (
                <EditUserModal
                    user={editingUser}
                    onSubmit={handleUpdateUser}
                    onClose={() => setEditingUser(null)}
                />
            )}
            {editingOrg && (
                <EditOrgModal
                    org={editingOrg}
                    onSubmit={handleUpdateOrg}
                    onClose={() => setEditingOrg(null)}
                />
            )}
            {showCreateInfra && (
                <CreateInfraModal
                    onSubmit={handleCreateInfra}
                    onClose={() => setShowCreateInfra(false)}
                />
            )}
            {editingInfra && (
                <EditInfraModal
                    infra={editingInfra}
                    onSubmit={handleUpdateInfra}
                    onClose={() => setEditingInfra(null)}
                />
            )}
            {editingRule && (
                <EditRuleModal
                    rule={editingRule}
                    onSubmit={handleUpdateRule}
                    onClose={() => setEditingRule(null)}
                />
            )}
        </div>
    )
}
