import { lazy, Suspense } from 'react'
import { createBrowserRouter } from 'react-router-dom'
import { Layout } from '@/components/Layout'
import { ProtectedRoute } from '@/components/ProtectedRoute'
import { ErrorBoundary } from '@/components/ui/ErrorBoundary'
import { Dashboard } from '@/pages/Dashboard'
import { Incidents } from '@/pages/Incidents'
import { SHM } from '@/pages/SHM'
import { APIHub } from '@/pages/APIHub'
import { Settings } from '@/pages/Settings'
import { Reports } from '@/pages/Reports'
import { Admin } from '@/pages/Admin'
import { Login } from '@/pages/Login'
import { NotFound } from '@/pages/NotFound'

const Prototype = lazy(() => import('@/pages/Prototype'))

/**
 * Wrap a page component in an ErrorBoundary so a crash in one page
 * doesn't take down the entire app (Layout + nav remain functional).
 */
function withErrorBoundary(element: React.ReactNode) {
    return <ErrorBoundary>{element}</ErrorBoundary>
}

export const router = createBrowserRouter([
    {
        path: '/login',
        element: <Login />,
    },
    {
        element: <ProtectedRoute />,
        children: [
            {
                path: '/',
                element: <Layout />,
                children: [
                    { index: true, element: withErrorBoundary(<Dashboard />) },
                    { path: 'api-hub', element: withErrorBoundary(<APIHub />) },
                    { path: 'incidents', element: withErrorBoundary(<Incidents />) },
                    { path: 'shm', element: withErrorBoundary(<SHM />) },
                    { path: 'reports', element: withErrorBoundary(<Reports />) },
                    { path: 'settings', element: withErrorBoundary(<Settings />) },
                    { path: 'admin', element: withErrorBoundary(<Admin />) },
                ],
            },
            {
                path: '/prototype',
                element: (
                    <Suspense fallback={<div className="w-screen h-screen bg-[#1a1a2e]" />}>
                        <Prototype />
                    </Suspense>
                ),
            },
        ],
    },
    {
        path: '*',
        element: <NotFound />,
    },
])
