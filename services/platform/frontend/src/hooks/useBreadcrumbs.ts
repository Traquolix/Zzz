import { useMemo } from 'react'
import { useLocation } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import type { BreadcrumbItem } from '@/components/ui/breadcrumb'

export function useBreadcrumbs(): BreadcrumbItem[] {
    const location = useLocation()
    const { t } = useTranslation()

    return useMemo(() => {
        const pathname = location.pathname

        // Root path - no breadcrumb
        if (pathname === '/') {
            return []
        }

        // Build breadcrumb trail
        const breadcrumbs: BreadcrumbItem[] = [
            { label: t('breadcrumb.home'), href: '/' },
        ]

        // Map paths to breadcrumb labels
        const pathToBreadcrumb: Record<string, string> = {
            '/incidents': t('nav.incidents'),
            '/shm': t('nav.shm'),
            '/reports': t('nav.reports'),
            '/api-hub': t('nav.apiData'),
            '/settings': t('nav.settings'),
            '/admin': t('nav.admin'),
        }

        const label = pathToBreadcrumb[pathname]
        if (label) {
            breadcrumbs.push({ label })
        }

        return breadcrumbs
    }, [location.pathname, t])
}
