import { useTranslation } from 'react-i18next'
import { useRealtime } from '@/hooks/useRealtime'
import { WifiOff, Loader2, ShieldAlert } from 'lucide-react'

export function ConnectionBanner() {
    const { connected, reconnecting, authFailed } = useRealtime()
    const { t } = useTranslation()

    if (connected) return null

    // Auth failure is a distinct, more severe state than simple disconnection
    if (authFailed) {
        return (
            <div
                role="alert"
                className="bg-red-50 border-b border-red-200 px-4 py-2 flex items-center justify-center gap-2 text-sm text-red-800"
            >
                <ShieldAlert className="h-4 w-4" aria-hidden="true" />
                <span>{t('connection.authFailed')}</span>
                <button
                    onClick={() => { window.location.href = '/login' }}
                    className="ml-2 px-3 py-1 bg-red-600 text-white text-xs font-medium rounded hover:bg-red-700 transition-colors pointer-events-auto"
                >
                    {t('connection.reLogin')}
                </button>
            </div>
        )
    }

    return (
        <div
            role="alert"
            className="bg-amber-50 border-b border-amber-200 px-4 py-2 flex items-center justify-center gap-2 text-sm text-amber-800"
        >
            {reconnecting ? (
                <>
                    <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                    <span>{t('connection.reconnecting')}</span>
                </>
            ) : (
                <>
                    <WifiOff className="h-4 w-4" aria-hidden="true" />
                    <span>{t('connection.disconnected')}</span>
                </>
            )}
        </div>
    )
}
