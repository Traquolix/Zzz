import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAuth } from '@/hooks/useAuth'
import { usePermissions } from '@/hooks/usePermissions'

export function ProtectedRoute() {
    const { isAuthenticated, isLoading } = useAuth()
    const { canAccessPage } = usePermissions()
    const location = useLocation()
    const { t } = useTranslation()

    if (isLoading) {
        return (
            <div className="min-h-screen flex items-center justify-center bg-background">
                <div className="text-foreground/50">{t('common.loading')}</div>
            </div>
        )
    }

    if (!isAuthenticated) {
        return <Navigate to="/login" replace />
    }

    // Page-level access: redirect to dashboard if user lacks the required widget
    if (!canAccessPage(location.pathname)) {
        return <Navigate to="/" replace />
    }

    return <Outlet />
}
