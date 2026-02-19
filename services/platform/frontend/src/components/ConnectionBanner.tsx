import { useTranslation } from 'react-i18next'
import { useRealtime } from '@/hooks/useRealtime'
import { WifiOff, Loader2 } from 'lucide-react'

export function ConnectionBanner() {
    const { connected, reconnecting } = useRealtime()
    const { t } = useTranslation()

    if (connected) return null

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
