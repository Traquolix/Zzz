import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { showToast } from '@/lib/toast'
import { fetchOrgSettings, updateOrgSettings } from '@/api/admin'
import { Button } from '@/components/ui/button'

export function SettingsPanel({ organizationId }: { organizationId: string }) {
    const { t } = useTranslation()
    const [loading, setLoading] = useState(true)
    const [saving, setSaving] = useState(false)

    const [timezone, setTimezone] = useState('')
    const [speedAlertThreshold, setSpeedAlertThreshold] = useState('')
    const [incidentAutoResolveMinutes, setIncidentAutoResolveMinutes] = useState('')
    const [shmEnabled, setShmEnabled] = useState(false)

    useEffect(() => {
        const loadSettings = async () => {
            try {
                setLoading(true)
                const data = await fetchOrgSettings(organizationId)
                setTimezone(data.timezone)
                setSpeedAlertThreshold(String(data.speedAlertThreshold))
                setIncidentAutoResolveMinutes(String(data.incidentAutoResolveMinutes))
                setShmEnabled(data.shmEnabled)
            } catch {
                showToast.error(t('common.error'))
            } finally {
                setLoading(false)
            }
        }
        loadSettings()
    }, [organizationId, t])

    const handleSave = async () => {
        try {
            setSaving(true)
            await updateOrgSettings(organizationId, {
                timezone,
                speedAlertThreshold: Number(speedAlertThreshold),
                incidentAutoResolveMinutes: Number(incidentAutoResolveMinutes),
                shmEnabled,
            })
            showToast.success(t('admin.settingsUpdated'))
        } catch {
            showToast.error(t('common.error'))
        } finally {
            setSaving(false)
        }
    }

    if (loading) {
        return <div className="text-center py-12 text-slate-400">{t('common.loading')}</div>
    }

    return (
        <div data-testid="settings-panel">
            <h2 className="text-lg font-medium text-slate-700 mb-6">{t('admin.tabs.settings')}</h2>
            <div className="bg-white rounded-lg border border-slate-200 p-6">
                <div className="space-y-4 max-w-2xl">
                    <div>
                        <label className="block text-sm font-medium text-slate-700 mb-1">
                            {t('admin.settings.timezone')}
                        </label>
                        <input
                            type="text"
                            value={timezone}
                            onChange={e => setTimezone(e.target.value)}
                            className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                            placeholder="UTC"
                        />
                    </div>

                    <div>
                        <label className="block text-sm font-medium text-slate-700 mb-1">
                            {t('admin.settings.speedAlertThreshold')}
                        </label>
                        <input
                            type="number"
                            value={speedAlertThreshold}
                            onChange={e => setSpeedAlertThreshold(e.target.value)}
                            className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                        />
                    </div>

                    <div>
                        <label className="block text-sm font-medium text-slate-700 mb-1">
                            {t('admin.settings.incidentAutoResolve')}
                        </label>
                        <input
                            type="number"
                            value={incidentAutoResolveMinutes}
                            onChange={e => setIncidentAutoResolveMinutes(e.target.value)}
                            className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                        />
                    </div>

                    <label className="flex items-center gap-2 text-sm text-slate-600 cursor-pointer">
                        <input
                            type="checkbox"
                            checked={shmEnabled}
                            onChange={e => setShmEnabled(e.target.checked)}
                            className="rounded border-slate-300 text-blue-600 focus:ring-blue-500"
                        />
                        {t('admin.settings.shmEnabled')}
                    </label>

                    <div className="pt-4">
                        <Button
                            onClick={handleSave}
                            isLoading={saving}
                            loadingText={t('common.loading')}
                        >
                            {t('admin.save')}
                        </Button>
                    </div>
                </div>
            </div>
        </div>
    )
}
