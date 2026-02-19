import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { DashboardHeader } from '@/components/Dashboard/DashboardHeader'
import { DashboardGrid } from '@/components/Dashboard/DashboardGrid'
import { useDashboard } from '@/hooks/useDashboard'
import { EditTooltip } from '@/components/Dashboard/Editing/EditTooltip'
import { DashboardProvider } from '@/context/DashboardContext'
import { DashboardDataProvider } from '@/context/DashboardDataProvider'

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
        return <div className="flex-1 flex items-center justify-center">{t('common.loading')}</div>
    }

    return (
        <DashboardProvider widgetIds={widgetIds}>
            <DashboardDataProvider>
                <div className="relative flex flex-col h-full min-h-0">
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
