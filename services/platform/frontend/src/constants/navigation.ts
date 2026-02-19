import type { LucideIcon } from 'lucide-react'
import { LayoutDashboard, AlertTriangle, FileText, Database, Settings, Building2 } from 'lucide-react'

export type NavItem = {
    path: string
    labelKey: string
    icon: LucideIcon
    end?: boolean
    requiredWidget?: string
    /** If this item has alternates, they share the same nav slot and swap on selection */
    alternates?: NavItem[]
}

/**
 * Single source of truth for navigable routes and their access requirements.
 * Used by: Layout (nav links), ProtectedRoute (route guard), usePermissions (filtering).
 *
 * Items with `alternates` create a hover dropdown where selecting an alternate
 * swaps it into the main nav position.
 */
export const NAV_ITEMS: NavItem[] = [
    { path: '/', labelKey: 'nav.monitoring', icon: LayoutDashboard, end: true },
    {
        path: '/incidents',
        labelKey: 'nav.incidents',
        icon: AlertTriangle,
        requiredWidget: 'incidents',
        alternates: [
            { path: '/shm', labelKey: 'nav.shm', icon: Building2, requiredWidget: 'shm' },
        ]
    },
    { path: '/reports', labelKey: 'nav.reports', icon: FileText, requiredWidget: 'incidents' },
    { path: '/apihub', labelKey: 'nav.apiData', icon: Database },
    { path: '/settings', labelKey: 'nav.settings', icon: Settings },
]
