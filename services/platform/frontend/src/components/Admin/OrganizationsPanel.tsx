import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { showToast } from '@/lib/toast'
import { AVAILABLE_WIDGETS, AVAILABLE_LAYERS } from '@/constants/permissions'
import {
    fetchOrgSettings,
    updateOrgSettings,
    fetchFiberAssignments,
    createFiberAssignment,
    deleteFiberAssignment,
} from '@/api/admin'
import type { AdminOrganization, OrgSettings, FiberAssignment } from '@/types/admin'
import { CheckboxGrid, ActiveBadge } from './shared'
import { EmptyState } from '@/components/ui/EmptyState'
import { Button } from '@/components/ui/button'

export function OrganizationsPanel({
    organizations,
    onCreateClick,
    onEditClick,
}: {
    organizations: AdminOrganization[]
    onCreateClick: () => void
    onEditClick: (org: AdminOrganization) => void
}) {
    const { t } = useTranslation()
    const [expandedOrgId, setExpandedOrgId] = useState<string | null>(null)
    const [orgSettingsData, setOrgSettingsData] = useState<Record<string, OrgSettings>>({})
    const [orgFibers, setOrgFibers] = useState<Record<string, FiberAssignment[]>>({})
    const [loadingOrgId, setLoadingOrgId] = useState<string | null>(null)

    const toggleExpand = async (orgId: string) => {
        if (expandedOrgId === orgId) {
            setExpandedOrgId(null)
            return
        }

        setLoadingOrgId(orgId)
        try {
            if (!orgSettingsData[orgId]) {
                const settings = await fetchOrgSettings(orgId)
                setOrgSettingsData(prev => ({ ...prev, [orgId]: settings }))
            }
            if (!orgFibers[orgId]) {
                const fibers = await fetchFiberAssignments(orgId)
                setOrgFibers(prev => ({ ...prev, [orgId]: fibers.results }))
            }
            setExpandedOrgId(orgId)
        } catch {
            showToast.error(t('common.error'))
        } finally {
            setLoadingOrgId(null)
        }
    }

    return (
        <div data-testid="organizations-panel">
            <div className="flex items-center justify-between mb-4">
                <h2 className="text-lg font-medium text-slate-700">{t('admin.tabs.organizations')}</h2>
                <button
                    onClick={onCreateClick}
                    className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors"
                >
                    {t('admin.createOrg')}
                </button>
            </div>
            {organizations.length === 0 ? (
                <EmptyState
                    title={t('admin.noOrgs')}
                    description={undefined}
                />
            ) : (
                <div className="space-y-4">
                    {organizations.map(org => (
                        <OrgCard
                            key={org.id}
                            org={org}
                            isExpanded={expandedOrgId === org.id}
                            isLoading={loadingOrgId === org.id}
                            onToggleExpand={() => toggleExpand(org.id)}
                            onEditClick={() => onEditClick(org)}
                            settings={orgSettingsData[org.id] || null}
                            fibers={orgFibers[org.id] || []}
                            onRefreshFibers={() => {
                                setOrgFibers(prev => ({ ...prev, [org.id]: [] }))
                                toggleExpand(org.id)
                            }}
                        />
                    ))}
                </div>
            )}
        </div>
    )
}

function OrgCard({
    org,
    isExpanded,
    isLoading,
    onToggleExpand,
    onEditClick,
    settings,
    fibers,
    onRefreshFibers,
}: {
    org: AdminOrganization
    isExpanded: boolean
    isLoading: boolean
    onToggleExpand: () => void
    onEditClick: () => void
    settings: OrgSettings | null
    fibers: FiberAssignment[]
    onRefreshFibers: () => void
}) {
    const { t } = useTranslation()
    const [editSettings, setEditSettings] = useState(false)
    const [savingSettings, setSavingSettings] = useState(false)
    const [newFiberId, setNewFiberId] = useState('')
    const [addingFiber, setAddingFiber] = useState(false)

    const [timezone, setTimezone] = useState(settings?.timezone || '')
    const [speedAlertThreshold, setSpeedAlertThreshold] = useState(String(settings?.speedAlertThreshold || ''))
    const [incidentAutoResolveMinutes, setIncidentAutoResolveMinutes] = useState(String(settings?.incidentAutoResolveMinutes || ''))
    const [shmEnabled, setShmEnabled] = useState(settings?.shmEnabled || false)
    const [allowedWidgets, setAllowedWidgets] = useState(settings?.allowedWidgets || [])
    const [allowedLayers, setAllowedLayers] = useState(settings?.allowedLayers || [])

    const handleSaveSettings = async () => {
        try {
            setSavingSettings(true)
            await updateOrgSettings(org.id, {
                timezone,
                speedAlertThreshold: Number(speedAlertThreshold),
                incidentAutoResolveMinutes: Number(incidentAutoResolveMinutes),
                shmEnabled,
                allowedWidgets,
                allowedLayers,
            })
            setEditSettings(false)
            showToast.success(t('admin.settingsUpdated'))
        } catch {
            showToast.error(t('common.error'))
        } finally {
            setSavingSettings(false)
        }
    }

    const handleAddFiber = async () => {
        if (!newFiberId.trim()) return
        try {
            setAddingFiber(true)
            await createFiberAssignment(org.id, newFiberId)
            showToast.success(t('admin.fiberAssigned'))
            setNewFiberId('')
            onRefreshFibers()
        } catch {
            showToast.error(t('common.error'))
        } finally {
            setAddingFiber(false)
        }
    }

    const handleDeleteFiber = async (assignmentId: string) => {
        try {
            await deleteFiberAssignment(org.id, assignmentId)
            showToast.success(t('admin.fiberRemoved'))
            onRefreshFibers()
        } catch {
            showToast.error(t('common.error'))
        }
    }

    return (
        <div className="bg-white rounded-lg border border-slate-200 overflow-hidden">
            <div
                className="px-6 py-4 flex items-center justify-between cursor-pointer hover:bg-slate-50"
                onClick={onToggleExpand}
            >
                <div className="flex items-center gap-4">
                    <div className={`transition-transform ${isExpanded ? 'rotate-90' : ''}`}>
                        {isLoading ? (
                            <div className="w-5 h-5 border-2 border-blue-600 border-t-transparent rounded-full animate-spin" />
                        ) : (
                            <svg className="w-5 h-5 text-slate-400" fill="currentColor" viewBox="0 0 20 20">
                                <path fillRule="evenodd" d="M7.293 14.707a1 1 0 010-1.414L10.586 10 7.293 6.707a1 1 0 011.414-1.414l4 4a1 1 0 010 1.414l-4 4a1 1 0 01-1.414 0z" />
                            </svg>
                        )}
                    </div>
                    <div>
                        <div className="flex items-center gap-2">
                            <h3 className="font-medium text-slate-700">{org.name}</h3>
                            <button
                                onClick={(e) => {
                                    e.stopPropagation()
                                    onEditClick()
                                }}
                                className="text-xs text-blue-600 hover:text-blue-800 font-medium"
                            >
                                {t('admin.edit')}
                            </button>
                        </div>
                        <p className="text-xs text-slate-500">{org.slug}</p>
                    </div>
                </div>
                <ActiveBadge isActive={org.isActive} />
            </div>

            {isExpanded && !isLoading && settings && (
                <div className="border-t border-slate-100 px-6 py-4 space-y-6 bg-slate-50">
                    {/* Settings Section */}
                    <div>
                        <h4 className="font-medium text-slate-700 mb-4">{t('admin.tabs.settings')}</h4>
                        {!editSettings ? (
                            <div className="space-y-2 text-sm text-slate-600">
                                <p>{t('admin.settings.timezoneLabel')} <span className="font-medium">{timezone || '—'}</span></p>
                                <p>{t('admin.settings.speedAlertLabel')} <span className="font-medium">{speedAlertThreshold || '—'} km/h</span></p>
                                <p>{t('admin.settings.autoResolveLabel')} <span className="font-medium">{incidentAutoResolveMinutes || '—'} min</span></p>
                                <p>{t('admin.settings.shmLabel')} <span className="font-medium">{shmEnabled ? t('admin.settings.enabled') : t('admin.settings.disabled')}</span></p>
                                <button
                                    onClick={() => setEditSettings(true)}
                                    className="text-xs text-blue-600 hover:text-blue-800 font-medium mt-2"
                                >
                                    {t('admin.edit')}
                                </button>
                            </div>
                        ) : (
                            <div className="space-y-4 bg-white p-4 rounded border border-slate-200">
                                <div>
                                    <label className="block text-xs font-medium text-slate-700 mb-1">
                                        {t('admin.settings.timezone')}
                                    </label>
                                    <input
                                        type="text"
                                        value={timezone}
                                        onChange={e => setTimezone(e.target.value)}
                                        className="w-full border border-slate-300 rounded px-2 py-1 text-sm"
                                    />
                                </div>
                                <div>
                                    <label className="block text-xs font-medium text-slate-700 mb-1">
                                        {t('admin.settings.speedAlertThreshold')}
                                    </label>
                                    <input
                                        type="number"
                                        value={speedAlertThreshold}
                                        onChange={e => setSpeedAlertThreshold(e.target.value)}
                                        className="w-full border border-slate-300 rounded px-2 py-1 text-sm"
                                    />
                                </div>
                                <div>
                                    <label className="block text-xs font-medium text-slate-700 mb-1">
                                        {t('admin.settings.incidentAutoResolve')}
                                    </label>
                                    <input
                                        type="number"
                                        value={incidentAutoResolveMinutes}
                                        onChange={e => setIncidentAutoResolveMinutes(e.target.value)}
                                        className="w-full border border-slate-300 rounded px-2 py-1 text-sm"
                                    />
                                </div>
                                <label className="flex items-center gap-2 text-sm text-slate-600 cursor-pointer">
                                    <input
                                        type="checkbox"
                                        checked={shmEnabled}
                                        onChange={e => setShmEnabled(e.target.checked)}
                                        className="rounded border-slate-300 text-blue-600"
                                    />
                                    {t('admin.settings.shmEnabled')}
                                </label>
                                <CheckboxGrid
                                    items={AVAILABLE_WIDGETS}
                                    selected={allowedWidgets}
                                    onChange={setAllowedWidgets}
                                    label={t('admin.settings.widgets')}
                                />
                                <CheckboxGrid
                                    items={AVAILABLE_LAYERS}
                                    selected={allowedLayers}
                                    onChange={setAllowedLayers}
                                    label={t('admin.settings.layers')}
                                />
                                <div className="flex gap-2 pt-2">
                                    <Button
                                        onClick={handleSaveSettings}
                                        isLoading={savingSettings}
                                        loadingText={t('common.loading')}
                                        size="sm"
                                    >
                                        {t('admin.save')}
                                    </Button>
                                    <button
                                        onClick={() => setEditSettings(false)}
                                        className="text-xs px-3 py-1 bg-slate-300 text-slate-700 rounded hover:bg-slate-400"
                                    >
                                        {t('common.cancel')}
                                    </button>
                                </div>
                            </div>
                        )}
                    </div>

                    {/* Fiber Assignments Section */}
                    <div>
                        <h4 className="font-medium text-slate-700 mb-4">{t('admin.settings.fibers.title')}</h4>
                        {fibers.length > 0 ? (
                            <div className="bg-white rounded border border-slate-200 mb-4">
                                <table className="w-full text-sm">
                                    <thead>
                                        <tr className="bg-slate-50 border-b border-slate-100">
                                            <th className="px-3 py-2 text-left text-xs font-medium text-slate-500">
                                                {t('admin.settings.fibers.fiberId')}
                                            </th>
                                            <th className="px-3 py-2 text-left text-xs font-medium text-slate-500">
                                                {t('admin.settings.fibers.assignedAt')}
                                            </th>
                                            <th className="px-3 py-2 text-left text-xs font-medium text-slate-500">
                                                {t('reports.actions')}
                                            </th>
                                        </tr>
                                    </thead>
                                    <tbody className="divide-y divide-slate-100">
                                        {fibers.map(assignment => (
                                            <tr key={assignment.id}>
                                                <td className="px-3 py-2 text-slate-700">{assignment.fiberId}</td>
                                                <td className="px-3 py-2 text-slate-500 text-xs">
                                                    {new Date(assignment.assignedAt).toLocaleDateString()}
                                                </td>
                                                <td className="px-3 py-2">
                                                    <button
                                                        onClick={() => handleDeleteFiber(assignment.id)}
                                                        className="text-xs text-red-600 hover:text-red-800 font-medium"
                                                    >
                                                        {t('common.delete')}
                                                    </button>
                                                </td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        ) : (
                            <p className="text-xs text-slate-500 mb-4">{t('admin.settings.fibers.noFibers')}</p>
                        )}
                        <div className="flex gap-2">
                            <input
                                type="text"
                                value={newFiberId}
                                onChange={e => setNewFiberId(e.target.value)}
                                placeholder={t('admin.settings.fibers.fiberId')}
                                className="flex-1 border border-slate-300 rounded px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                            />
                            <Button
                                onClick={handleAddFiber}
                                disabled={!newFiberId.trim()}
                                isLoading={addingFiber}
                                loadingText={t('common.loading')}
                                size="sm"
                            >
                                {t('admin.settings.fibers.addFiber')}
                            </Button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    )
}
