import { useTranslation } from 'react-i18next'

interface TabsProps {
    activeTab: 'landmarks' | 'sections'
    hasLandmarks: number
    hasSections: number
    onTabChange: (tab: 'landmarks' | 'sections') => void
}

export function TrafficTabs({ activeTab, hasLandmarks, hasSections, onTabChange }: TabsProps) {
    const { t } = useTranslation()
    return (
        <div className="flex-shrink-0 flex border-b border-slate-200 bg-slate-50">
            <button
                onClick={() => onTabChange('landmarks')}
                className={`flex-1 px-4 py-2 text-xs font-medium transition-colors relative ${
                    activeTab === 'landmarks'
                        ? 'text-blue-600 bg-white'
                        : 'text-slate-500 hover:text-slate-700 hover:bg-slate-100'
                }`}
            >
                <div className="flex items-center justify-center gap-1.5">
                    <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
                    </svg>
                    {t('traffic.tabs.landmarks')}
                    {hasLandmarks > 0 && (
                        <span className={`ml-1 px-1.5 py-0.5 rounded-full text-[10px] ${
                            activeTab === 'landmarks' ? 'bg-blue-100 text-blue-600' : 'bg-slate-200 text-slate-500'
                        }`}>
                            {hasLandmarks}
                        </span>
                    )}
                </div>
                {activeTab === 'landmarks' && (
                    <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-blue-500" />
                )}
            </button>
            <button
                onClick={() => onTabChange('sections')}
                className={`flex-1 px-4 py-2 text-xs font-medium transition-colors relative ${
                    activeTab === 'sections'
                        ? 'text-blue-600 bg-white'
                        : 'text-slate-500 hover:text-slate-700 hover:bg-slate-100'
                }`}
            >
                <div className="flex items-center justify-center gap-1.5">
                    <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l4.553 2.276A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 4m0 13V4m0 0L9 7" />
                    </svg>
                    {t('traffic.tabs.sections')}
                    {hasSections > 0 && (
                        <span className={`ml-1 px-1.5 py-0.5 rounded-full text-[10px] ${
                            activeTab === 'sections' ? 'bg-blue-100 text-blue-600' : 'bg-slate-200 text-slate-500'
                        }`}>
                            {hasSections}
                        </span>
                    )}
                </div>
                {activeTab === 'sections' && (
                    <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-blue-500" />
                )}
            </button>
        </div>
    )
}

interface EmptyStateProps {
    activeTab: 'landmarks' | 'sections'
}

export function TrafficEmptyState({ activeTab }: EmptyStateProps) {
    const { t } = useTranslation()
    return (
        <div className="flex-1 flex items-center justify-center text-slate-400 text-sm bg-gradient-to-b from-slate-50 to-white">
            <div className="text-center px-4">
                {activeTab === 'landmarks' ? (
                    <>
                        <svg className="w-10 h-10 mx-auto mb-2 text-slate-200" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
                        </svg>
                        <div className="font-medium text-slate-500 mb-1">{t('traffic.empty.noLandmarks')}</div>
                        <div className="text-xs text-slate-400">{t('traffic.empty.createLandmarkHint')}</div>
                    </>
                ) : (
                    <>
                        <svg className="w-10 h-10 mx-auto mb-2 text-slate-200" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l4.553 2.276A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 4m0 13V4m0 0L9 7" />
                        </svg>
                        <div className="font-medium text-slate-500 mb-1">{t('traffic.empty.noSections')}</div>
                        <div className="text-xs text-slate-400">{t('traffic.empty.createSectionHint')}</div>
                    </>
                )}
            </div>
        </div>
    )
}

interface SelectionPromptProps {
    activeTab: 'landmarks' | 'sections'
}

export function TrafficSelectionPrompt({ activeTab }: SelectionPromptProps) {
    const { t } = useTranslation()
    return (
        <div className="flex-1 flex items-center justify-center text-slate-400 text-sm">
            <div className="text-center px-4">
                <svg className="w-8 h-8 mx-auto mb-2 text-slate-200" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 15l-2 5L9 9l11 4-5 2zm0 0l5 5M7.188 2.239l.777 2.897M5.136 7.965l-2.898-.777M13.95 4.05l-2.122 2.122m-5.657 5.656l-2.12 2.122" />
                </svg>
                <div className="text-xs leading-relaxed">
                    {activeTab === 'landmarks' ? (
                        <>
                            {t('traffic.prompt.selectLandmark')}<br />
                            {t('traffic.prompt.selectLandmarkHint')}
                        </>
                    ) : (
                        <>
                            {t('traffic.prompt.selectSection')}<br />
                            {t('traffic.prompt.selectSectionHint')}
                        </>
                    )}
                </div>
            </div>
        </div>
    )
}
