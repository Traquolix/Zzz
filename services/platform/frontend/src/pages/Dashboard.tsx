import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { DashboardHeader } from '@/components/Dashboard/DashboardHeader'
import { DashboardGrid } from '@/components/Dashboard/DashboardGrid'
import { useDashboard } from '@/hooks/useDashboard'
import { EditTooltip } from '@/components/Dashboard/Editing/EditTooltip'
import { DashboardProvider } from '@/context/DashboardContext'
import { DashboardDataProvider } from '@/context/DashboardDataProvider'
import { Skeleton } from '@/components/ui/Skeleton'
import { EmptyState } from '@/components/ui/EmptyState'

export function Dashboard() {
    const { t } = useTranslation()
    const {
        editMode,
        toggleEditMode,
        widgets,
        layouts,
        handleLayoutChange,
        addWidget,
        deleteWidget,
        isLoading,
    } = useDashboard()

    const widgetIds = useMemo(() => widgets.map(w => w.id), [widgets])

    if (isLoading) {
        return (
            <div className="flex-1 p-4" role="status">
                <div className="flex items-center justify-between mb-4">
                    <Skeleton pattern="line" className="w-48 h-8" />
                    <Skeleton pattern="line" className="w-24 h-8" />
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                    {Array.from({ length: 6 }, (_, i) => (
                        <div key={i} className="bg-white dark:bg-slate-900 rounded-lg border border-slate-200 dark:border-slate-700 p-4 h-48">
                            <Skeleton pattern="card" />
                        </div>
                    ))}
                </div>
                <span className="sr-only">{t('common.loading')}</span>
            </div>
        )
    }

    if (widgets.length === 0 && !editMode) {
        return (
            <div className="relative flex flex-col h-full min-h-0">
                <DashboardHeader
                    editMode={editMode}
                    onToggle={toggleEditMode}
                    onAddWidget={editMode ? addWidget : undefined}
                />
                <div className="flex-1 flex items-center justify-center">
                    <EmptyState
                        title={t('dashboard.empty', 'Your dashboard is empty')}
                        description={t('dashboard.emptyDescription', 'Click Edit to add widgets and customize your view.')}
                    />
                </div>
            </div>
        )
    }

    return (
        <DashboardProvider widgetIds={widgetIds}>
            <DashboardDataProvider>
                <div className="relative flex flex-col h-full min-h-0 animate-in fade-in-0 duration-300" aria-busy="false">
                    <DashboardHeader
                        editMode={editMode}
                        onToggle={toggleEditMode}
                        onAddWidget={editMode ? addWidget : undefined}
                    />
                    <DashboardGrid
                        widgets={widgets}
                        layouts={layouts}
                        editMode={editMode}
                        onLayoutChange={handleLayoutChange}
                        onDeleteWidget={editMode ? deleteWidget : undefined}
                    />
                    <EditTooltip visible={editMode} />
                </div>
            </DashboardDataProvider>
        </DashboardProvider>
    )
}
