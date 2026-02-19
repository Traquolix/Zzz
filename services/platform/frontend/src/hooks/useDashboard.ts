import { useState, useEffect, useCallback } from 'react'
import type { Layout } from 'react-grid-layout'
import { WIDGET_REGISTRY, DEFAULT_WIDGETS, DEFAULT_LAYOUTS, COLS } from '@/constants/dashboard'
import type { WidgetConfig, Layouts } from "@/types/dashboard"
import { useUserPreferences } from './useUserPreferences'
import { usePermissions } from './usePermissions'

type LayoutItem = { i: string; x: number; y: number; w: number; h: number }

function widgetIdsToConfigs(widgetIds: string[], allowedWidgets: string[]): WidgetConfig[] {
    return widgetIds
        .filter(id => {
            const type = id.includes('-') ? id.split('-')[0] : id
            return allowedWidgets.includes(type) && WIDGET_REGISTRY[type]
        })
        .map(id => {
            const type = id.includes('-') ? id.split('-')[0] : id
            const registry = WIDGET_REGISTRY[type]
            return { id, name: registry.name, component: registry.component }
        })
}

export function useDashboard() {
    const { preferences, updatePreferences, isLoading: prefsLoading } = useUserPreferences()
    const { allowedWidgets } = usePermissions()

    const [editMode, setEditMode] = useState(false)
    const [widgets, setWidgets] = useState<WidgetConfig[]>([])
    const [layouts, setLayouts] = useState<Layouts>(DEFAULT_LAYOUTS)
    const [initialized, setInitialized] = useState(false)

    // Initialize from preferences or defaults (once preferences are loaded)
    useEffect(() => {
        if (prefsLoading || initialized) return
        setInitialized(true)

        const savedWidgets = preferences?.dashboard?.widgets
        const savedLayouts = preferences?.dashboard?.layouts

        if (savedWidgets?.length) {
            setWidgets(widgetIdsToConfigs(savedWidgets, allowedWidgets))
        } else {
            setWidgets(DEFAULT_WIDGETS.filter(w => allowedWidgets.includes(w.id)))
        }

        if (savedLayouts && Object.keys(savedLayouts).length > 0) {
            setLayouts(savedLayouts as Layouts)
        }
    }, [prefsLoading, preferences, allowedWidgets, initialized])

    // Save current state to server
    const save = useCallback(() => {
        updatePreferences({
            ...preferences,
            dashboard: {
                widgets: widgets.map(w => w.id),
                layouts: layouts as Record<string, LayoutItem[]>
            }
        })
    }, [preferences, updatePreferences, widgets, layouts])

    // Toggle edit mode - save when exiting
    const toggleEditMode = useCallback(() => {
        if (editMode) {
            // Exiting edit mode - save
            save()
        }
        setEditMode(prev => !prev)
    }, [editMode, save])

    const handleLayoutChange = useCallback((_currentLayout: Layout, allLayouts: Layouts) => {
        setLayouts(allLayouts)
    }, [])

    const addWidget = useCallback((type: keyof typeof WIDGET_REGISTRY) => {
        if (!allowedWidgets.includes(type)) return

        const id = `${type}-${Date.now()}`
        const registry = WIDGET_REGISTRY[type]
        const newWidget: WidgetConfig = { id, name: registry.name, component: registry.component }

        setWidgets(prev => [...prev, newWidget])

        // Add to all breakpoint layouts at bottom
        setLayouts(prev => {
            const updated: Layouts = {}
            for (const [bp, items] of Object.entries(prev)) {
                const list = (items || []) as LayoutItem[]
                const maxY = list.length ? Math.max(...list.map(i => i.y + i.h)) : 0
                const cols = COLS[bp as keyof typeof COLS] || 12
                updated[bp] = [...list, {
                    i: id,
                    x: 0,
                    y: maxY,
                    w: Math.min(registry.defaultSize.w, cols),
                    h: registry.defaultSize.h
                }]
            }
            return updated
        })
    }, [allowedWidgets])

    const deleteWidget = useCallback((id: string) => {
        setWidgets(prev => prev.filter(w => w.id !== id))
        setLayouts(prev => {
            const updated: Layouts = {}
            for (const [bp, items] of Object.entries(prev)) {
                updated[bp] = ((items || []) as LayoutItem[]).filter(i => i.i !== id)
            }
            return updated
        })
    }, [])

    return {
        editMode,
        toggleEditMode,
        widgets,
        layouts,
        handleLayoutChange,
        addWidget,
        deleteWidget,
        isLoading: prefsLoading || !initialized,
    }
}
