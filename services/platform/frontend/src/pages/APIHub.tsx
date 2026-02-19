import { useTranslation } from 'react-i18next'
import { useAuth } from '@/hooks/useAuth'
import { API_URL } from '@/constants/api'

const ENDPOINTS = [
    { method: 'GET', path: '/api/detections', labelKey: 'detections' },
    { method: 'GET', path: '/api/incidents', labelKey: 'incidents' },
    { method: 'GET', path: '/api/fibers', labelKey: 'fibers' },
    { method: 'GET', path: '/api/speed-stats', labelKey: 'speedStats' },
    { method: 'GET', path: '/api/reports', labelKey: 'reports' },
] as const

const METHOD_COLORS: Record<string, string> = {
    GET: 'bg-green-100 text-green-700',
    POST: 'bg-blue-100 text-blue-700',
    PUT: 'bg-amber-100 text-amber-700',
    DELETE: 'bg-red-100 text-red-700',
}

export function APIHub() {
    const { t } = useTranslation()
    const { organizationName } = useAuth()

    return (
        <div className="flex-1 overflow-y-auto bg-slate-50">
            <div className="max-w-4xl mx-auto px-6 py-8 space-y-8">
                {/* Page header */}
                <div>
                    <h1 className="text-2xl font-bold text-slate-800">{t('apiHub.title')}</h1>
                    <p className="mt-2 text-slate-500 text-sm leading-relaxed max-w-2xl">
                        {t('apiHub.description')}
                    </p>
                </div>

                {/* Authentication section */}
                <section className="bg-white rounded-lg border border-slate-200 overflow-hidden">
                    <div className="px-5 py-4 border-b border-slate-100">
                        <h2 className="text-sm font-semibold text-slate-700">{t('apiHub.authentication')}</h2>
                        <p className="text-xs text-slate-400 mt-1">{t('apiHub.authDescription')}</p>
                    </div>
                    <div className="px-5 py-4 space-y-3">
                        <div>
                            <div className="text-xs font-medium text-slate-500 mb-1">{t('apiHub.baseUrl')}</div>
                            <code className="block text-sm bg-slate-50 text-slate-700 px-3 py-2 rounded border border-slate-200 font-mono">
                                {API_URL}
                            </code>
                        </div>
                        {organizationName && (
                            <div className="flex items-center gap-2 text-xs text-slate-400">
                                <span className="w-2 h-2 rounded-full bg-green-400" />
                                {organizationName}
                            </div>
                        )}
                    </div>
                </section>

                {/* Endpoints section */}
                <section className="bg-white rounded-lg border border-slate-200 overflow-hidden">
                    <div className="px-5 py-4 border-b border-slate-100">
                        <h2 className="text-sm font-semibold text-slate-700">{t('apiHub.endpoints')}</h2>
                    </div>
                    <div className="divide-y divide-slate-100">
                        {ENDPOINTS.map((ep) => (
                            <div key={ep.path} className="px-5 py-3 flex items-center gap-4">
                                <span className={`text-[10px] font-bold uppercase tracking-wide px-2 py-0.5 rounded ${METHOD_COLORS[ep.method] ?? 'bg-slate-100 text-slate-600'}`}>
                                    {ep.method}
                                </span>
                                <code className="text-sm font-mono text-slate-700 flex-1">{ep.path}</code>
                                <span className="text-xs text-slate-400 hidden sm:block">
                                    {t(`apiHub.endpointList.${ep.labelKey}`)}
                                </span>
                            </div>
                        ))}
                    </div>
                </section>

                {/* Rate limits */}
                <section className="bg-white rounded-lg border border-slate-200 overflow-hidden">
                    <div className="px-5 py-4 border-b border-slate-100">
                        <h2 className="text-sm font-semibold text-slate-700">{t('apiHub.rateLimits')}</h2>
                    </div>
                    <div className="px-5 py-4">
                        <p className="text-xs text-slate-500 leading-relaxed">{t('apiHub.rateLimitsDescription')}</p>
                        <div className="mt-3 inline-flex items-center gap-2 bg-slate-50 border border-slate-200 rounded px-3 py-1.5">
                            <span className="text-sm font-mono font-semibold text-slate-700">{t('apiHub.requestsPerMinute', { count: 60 })}</span>
                        </div>
                    </div>
                </section>

                {/* Documentation link */}
                <section className="bg-white rounded-lg border border-slate-200 px-5 py-4">
                    <div className="flex items-start gap-4">
                        <div className="w-10 h-10 rounded-lg bg-blue-50 flex items-center justify-center flex-shrink-0">
                            <svg className="w-5 h-5 text-blue-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
                            </svg>
                        </div>
                        <div>
                            <h3 className="text-sm font-semibold text-slate-700">{t('apiHub.docsLink')}</h3>
                            <p className="text-xs text-slate-400 mt-0.5">{t('apiHub.docsDescription')}</p>
                        </div>
                    </div>
                </section>

                {/* Footer note */}
                <p className="text-center text-xs text-slate-400 pb-4">{t('apiHub.comingSoon')}</p>
            </div>
        </div>
    )
}
