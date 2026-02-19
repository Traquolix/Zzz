import { useMemo, useCallback } from 'react'
import { useAuth } from './useAuth'
import { NAV_ITEMS, type NavItem } from '@/constants/navigation'

/**
 * Centralized permission hook.
 *
 * Provides widget/layer access checks, page-level access logic,
 * and the filtered list of nav items — all derived from the
 * auth context's allowedWidgets and allowedLayers arrays.
 */
export function usePermissions() {
    const { allowedWidgets, allowedLayers } = useAuth()

    const hasWidget = useCallback(
        (widget: string) => allowedWidgets.includes(widget),
        [allowedWidgets],
    )

    const hasLayer = useCallback(
        (layer: string) => allowedLayers.includes(layer),
        [allowedLayers],
    )

    /** Can the user access this page path? */
    const canAccessPage = useCallback(
        (path: string): boolean => {
            const normalizedPath = path.toLowerCase()

            // Check main nav items
            const mainItem = NAV_ITEMS.find(n => n.path.toLowerCase() === normalizedPath)
            if (mainItem) {
                if (!mainItem.requiredWidget) return true
                return allowedWidgets.includes(mainItem.requiredWidget)
            }

            // Check alternates within nav items
            for (const item of NAV_ITEMS) {
                const alternate = item.alternates?.find(a => a.path.toLowerCase() === normalizedPath)
                if (alternate) {
                    if (!alternate.requiredWidget) return true
                    return allowedWidgets.includes(alternate.requiredWidget)
                }
            }

            // unknown route → let router handle 404
            return true
        },
        [allowedWidgets],
    )

    /** Nav items the user is allowed to see */
    const visibleNavItems: NavItem[] = useMemo(
        () =>
            NAV_ITEMS.filter(
                item => !item.requiredWidget || allowedWidgets.includes(item.requiredWidget),
            ),
        [allowedWidgets],
    )

    return { hasWidget, hasLayer, canAccessPage, visibleNavItems, allowedWidgets, allowedLayers }
}
