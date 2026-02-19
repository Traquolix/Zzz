import { RouterProvider } from 'react-router-dom'
import { Toaster } from 'sonner'
import { router } from './router/Router'
import { AuthProvider } from '@/context/AuthProvider'
import { UserPreferencesProvider } from '@/context/UserPreferencesProvider'
import { RealtimeProvider } from '@/context/RealtimeProvider'
import { SpeedLimitProvider } from '@/context/SpeedLimitProvider'
import { ConfirmDialogProvider } from '@/components/ui/confirm-dialog'
import { ErrorBoundary } from '@/components/ui/ErrorBoundary'
import { WS_URL } from '@/constants/api'
import '@/i18n'

/**
 * Top-level error fallback shown when the entire app crashes.
 * Provides a way to reload the page and recover.
 */
function AppErrorFallback() {
    return (
        <div className="flex flex-col items-center justify-center min-h-screen bg-slate-100 p-6">
            <div className="text-red-500 mb-4">
                <svg className="w-16 h-16" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
            </div>
            <h1 className="text-2xl font-bold text-slate-800 mb-2">Application Error</h1>
            <p className="text-slate-600 mb-6 text-center max-w-md">
                Something went wrong and the application could not recover. Please reload the page to try again.
            </p>
            <button
                onClick={() => window.location.reload()}
                className="px-6 py-3 bg-blue-500 text-white font-medium rounded-lg hover:bg-blue-600 transition-colors"
            >
                Reload Page
            </button>
        </div>
    )
}

function App() {
    return (
        <ErrorBoundary
            fallback={<AppErrorFallback />}
            onError={(error, errorInfo) => {
                // Log to console in development, could send to error tracking service in production
                console.error('App crashed:', error, errorInfo)
            }}
        >
            <AuthProvider>
                <UserPreferencesProvider>
                    <ConfirmDialogProvider>
                        <SpeedLimitProvider>
                            <RealtimeProvider url={WS_URL}>
                                <RouterProvider router={router} />
                                <Toaster position="bottom-right" richColors closeButton />
                            </RealtimeProvider>
                        </SpeedLimitProvider>
                    </ConfirmDialogProvider>
                </UserPreferencesProvider>
            </AuthProvider>
        </ErrorBoundary>
    )
}

export default App