import { useTranslation } from 'react-i18next'
import { Lock, LockOpen, Plus } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { WIDGET_REGISTRY } from '@/constants/dashboard'
import { usePermissions } from '@/hooks/usePermissions'

type Props = {
    editMode: boolean
    onToggle: () => void
    onAddWidget?: (type: string) => void
}

export function DashboardHeader({ editMode, onToggle, onAddWidget }: Props) {
    const { allowedWidgets } = usePermissions()
    const { t } = useTranslation()

    // Filter widgets by user permissions
    const availableWidgets = Object.entries(WIDGET_REGISTRY).filter(
        ([type]) => allowedWidgets.includes(type)
    )

    return (
        <div className="h-12 px-6 flex items-center justify-end gap-2 border-b bg-white relative z-20">
            {onAddWidget && availableWidgets.length > 0 && (
                <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                        <Button variant="outline" size="sm" className="gap-2">
                            <Plus className="h-4 w-4" />
                            {t('dashboard.addWidget')}
                        </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end" className="z-50">
                        {availableWidgets.map(([type, { icon: Icon }]) => (
                            <DropdownMenuItem
                                key={type}
                                onClick={() => onAddWidget(type)}
                                className="whitespace-nowrap gap-2 py-1.5"
                            >
                                <Icon className="h-4 w-4 text-slate-500" />
                                {t(`dashboard.widgets.${type}`)}
                            </DropdownMenuItem>
                        ))}
                    </DropdownMenuContent>
                </DropdownMenu>
            )}

            <Button
                variant={editMode ? 'default' : 'outline'}
                size="sm"
                onClick={onToggle}
                className="gap-2"
            >
                {editMode ? (
                    <>
                        <LockOpen className="h-4 w-4" />
                        {t('dashboard.editing')}
                    </>
                ) : (
                    <>
                        <Lock className="h-4 w-4" />
                        {t('dashboard.locked')}
                    </>
                )}
            </Button>
        </div>
    )
}
