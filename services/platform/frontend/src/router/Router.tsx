import { lazy, Suspense } from 'react'
import { createBrowserRouter, Navigate } from 'react-router-dom'
import { ProtectedRoute } from '@/components/ProtectedRoute'
import { ErrorBoundary } from '@/components/ui/ErrorBoundary'
import { Login } from '@/pages/Login'

const Dashboard = lazy(() => import('@/pages/Dashboard'))

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
        element: (
          <ErrorBoundary>
            <Suspense fallback={<div className="w-screen h-screen bg-[#1a1c20]" />}>
              <Dashboard />
            </Suspense>
          </ErrorBoundary>
        ),
      },
    ],
  },
  {
    path: '*',
    element: <Navigate to="/" replace />,
  },
])
