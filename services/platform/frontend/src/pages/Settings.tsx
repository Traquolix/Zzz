import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { SpeedLimitSettings } from '@/components/Settings/SpeedLimitSettings'

type CollapsibleSectionProps = {
    title: string
    children: React.ReactNode
    defaultOpen?: boolean
}

function CollapsibleSection({ title, children, defaultOpen = false }: CollapsibleSectionProps) {
    const [isOpen, setIsOpen] = useState(defaultOpen)

    return (
        <div className="border border-slate-200 dark:border-slate-700 rounded-lg overflow-hidden">
            <button
                onClick={() => setIsOpen(!isOpen)}
                className="w-full px-4 py-3 flex items-center justify-between bg-slate-50 dark:bg-slate-800 hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors"
            >
                <span className="font-medium text-slate-700 dark:text-slate-200">{title}</span>
                <svg
                    className={`w-5 h-5 text-slate-500 dark:text-slate-400 transition-transform ${isOpen ? 'rotate-180' : ''}`}
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                >
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                </svg>
            </button>
            {isOpen && (
                <div className="p-4 bg-white dark:bg-slate-900">
                    {children}
                </div>
            )}
        </div>
    )
}

export function Settings() {
    const { t } = useTranslation()

    return (
        <div className="h-full overflow-auto bg-slate-100 dark:bg-slate-950">
            <div className="max-w-6xl mx-auto p-6">
                <h1 className="text-2xl font-semibold text-slate-800 dark:text-slate-100 mb-6">{t('settings.title')}</h1>

                <div className="space-y-4">
                    <CollapsibleSection title={t('settings.speedLimits')} defaultOpen={true}>
                        <SpeedLimitSettings />
                    </CollapsibleSection>

                    {/* Future settings sections can be added here */}
                </div>
            </div>
        </div>
    )
}
