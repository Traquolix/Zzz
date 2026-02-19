import { createBrowserRouter } from 'react-router-dom'
import { Layout } from '@/components/Layout'
import { ProtectedRoute } from '@/components/ProtectedRoute'
import { Dashboard } from '@/pages/Dashboard'
import { Incidents } from '@/pages/Incidents'
import { SHM } from '@/pages/SHM'
import { APIHub } from '@/pages/APIHub'
import { Settings } from '@/pages/Settings'
import { Reports } from '@/pages/Reports'
import { Login } from '@/pages/Login'
import { NotFound } from '@/pages/NotFound'

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
                    { index: true, element: <Dashboard /> },
                    { path: 'ApiHub', element: <APIHub /> },
                    { path: 'Incidents', element: <Incidents /> },
                    { path: 'SHM', element: <SHM /> },
                    { path: 'Reports', element: <Reports /> },
                    { path: 'Settings', element: <Settings /> },
                ],
            },
        ],
    },
    {
        path: '*',
        element: <NotFound />,
    },
])