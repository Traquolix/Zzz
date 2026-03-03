import { useTranslation } from 'react-i18next'
import { Copy, Check } from 'lucide-react'
import { useAuth } from '@/hooks/useAuth'
import { useCopyToClipboard } from '@/hooks/useCopyToClipboard'
import { API_URL } from '@/constants/api'
import { Button } from '@/components/ui/button'
import { Tooltip } from '@/components/ui/tooltip'

const ENDPOINTS = [
    { method: 'GET', path: '/api/fibers', labelKey: 'fibers' },
    { method: 'GET', path: '/api/incidents', labelKey: 'incidents' },
    { method: 'GET', path: '/api/stats', labelKey: 'stats' },
    { method: 'GET', path: '/api/infrastructure', labelKey: 'infrastructure' },
    { method: 'GET', path: '/api/reports', labelKey: 'reports' },
    { method: 'GET', path: '/api/export/incidents', labelKey: 'exportIncidents' },
    { method: 'GET', path: '/api/export/speeds', labelKey: 'exportSpeeds' },
    { method: 'GET', path: '/api/export/counts', labelKey: 'exportCounts' },
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
    const { copy, isCopied } = useCopyToClipboard()

    return (
        <div className="flex-1 overflow-y-auto bg-slate-50 dark:bg-slate-950">
            <div className="max-w-4xl mx-auto px-6 py-8 space-y-8">
                {/* Page header */}
                <div>
                    <h1 className="text-2xl font-bold text-slate-800 dark:text-slate-100">{t('apiHub.title')}</h1>
                    <p className="mt-2 text-slate-500 dark:text-slate-400 text-sm leading-relaxed max-w-2xl">
                        {t('apiHub.description')}
                    </p>
                </div>

                {/* Authentication section */}
                <section className="bg-white dark:bg-slate-900 rounded-lg border border-slate-200 dark:border-slate-700 overflow-hidden">
                    <div className="px-5 py-4 border-b border-slate-100 dark:border-slate-800">
                        <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-200">{t('apiHub.authentication')}</h2>
                        <p className="text-xs text-slate-400 dark:text-slate-500 mt-1">{t('apiHub.authDescription')}</p>
                    </div>
                    <div className="px-5 py-4 space-y-3">
                        <div>
                            <div className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1">{t('apiHub.baseUrl')}</div>
                            <div className="flex items-center gap-2">
                                <code className="block text-sm bg-slate-50 dark:bg-slate-800 text-slate-700 dark:text-slate-300 px-3 py-2 rounded border border-slate-200 dark:border-slate-700 font-mono flex-1">
                                    {API_URL}
                                </code>
                                <Tooltip content={isCopied(API_URL) ? 'Copied!' : 'Copy URL'}>
                                    <Button
                                        variant="ghost"
                                        size="icon"
                                        onClick={() => copy(API_URL)}
                                        className="h-9 w-9"
                                    >
                                        {isCopied(API_URL) ? (
                                            <Check className="h-4 w-4 text-green-600 dark:text-green-400" />
                                        ) : (
                                            <Copy className="h-4 w-4" />
                                        )}
                                    </Button>
                                </Tooltip>
                            </div>
                        </div>
                        {organizationName && (
                            <div className="flex items-center gap-2 text-xs text-slate-400">
                                <span className="w-2 h-2 rounded-full bg-green-400" />
                                {organizationName}
                            </div>
                        )}
                    </div>
                </section>

                {/* API Key Authentication */}
                <section className="bg-white dark:bg-slate-900 rounded-lg border border-slate-200 dark:border-slate-700 overflow-hidden">
                    <div className="px-5 py-4 border-b border-slate-100 dark:border-slate-800">
                        <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-200">{t('apiHub.apiKeyAuth')}</h2>
                        <p className="text-xs text-slate-400 dark:text-slate-500 mt-1">{t('apiHub.apiKeyDescription')}</p>
                    </div>
                    <div className="px-5 py-4 space-y-3">
                        <div className="text-xs text-slate-500 dark:text-slate-400 leading-relaxed space-y-2">
                            <p>Send the <code className="bg-slate-100 dark:bg-slate-800 px-1.5 py-0.5 rounded font-mono text-slate-700 dark:text-slate-300">X-API-Key</code> header with your API key:</p>
                            <pre className="bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded p-3 text-xs font-mono text-slate-700 dark:text-slate-300 overflow-x-auto">
{`curl -H "X-API-Key: sqk_your_key_here" \\
     ${API_URL}/api/incidents`}
                            </pre>
                            <p>API keys are read-only (viewer role). Create and manage keys in Settings &gt; API Keys.</p>
                        </div>
                    </div>
                </section>

                {/* Endpoints section */}
                <section className="bg-white dark:bg-slate-900 rounded-lg border border-slate-200 dark:border-slate-700 overflow-hidden">
                    <div className="px-5 py-4 border-b border-slate-100 dark:border-slate-800">
                        <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-200">{t('apiHub.endpoints')}</h2>
                    </div>
                    <div className="divide-y divide-slate-100 dark:divide-slate-800">
                        {ENDPOINTS.map((ep) => (
                                <div key={ep.path} className="px-5 py-3 flex items-center gap-4">
                                    <span className={`text-[10px] font-bold uppercase tracking-wide px-2 py-0.5 rounded ${METHOD_COLORS[ep.method] ?? 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400'}`}>
                                        {ep.method}
                                    </span>
                                    <code className="text-sm font-mono text-slate-700 dark:text-slate-300 flex-1">{ep.path}</code>
                                    <div className="flex items-center gap-2">
                                        <span className="text-xs text-slate-400 dark:text-slate-500 hidden sm:block">
                                            {t(`apiHub.endpointList.${ep.labelKey}`)}
                                        </span>
                                        <Tooltip content={isCopied(ep.path) ? 'Copied!' : 'Copy URL'}>
                                            <Button
                                                variant="ghost"
                                                size="icon"
                                                onClick={() => copy(ep.path)}
                                                className="h-8 w-8"
                                            >
                                                {isCopied(ep.path) ? (
                                                    <Check className="h-4 w-4 text-green-600 dark:text-green-400" />
                                                ) : (
                                                    <Copy className="h-4 w-4" />
                                                )}
                                            </Button>
                                        </Tooltip>
                                    </div>
                                </div>
                        ))}
                    </div>
                </section>

                {/* Webhook section */}
                <section className="bg-white dark:bg-slate-900 rounded-lg border border-slate-200 dark:border-slate-700 overflow-hidden">
                    <div className="px-5 py-4 border-b border-slate-100 dark:border-slate-800">
                        <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-200">{t('apiHub.webhooks')}</h2>
                        <p className="text-xs text-slate-400 dark:text-slate-500 mt-1">{t('apiHub.webhookDescription')}</p>
                    </div>
                    <div className="px-5 py-4 space-y-3">
                        <div className="text-xs text-slate-500 dark:text-slate-400 leading-relaxed space-y-2">
                            <p>When a webhook secret is configured, each payload is signed with HMAC-SHA256. Verify using the <code className="bg-slate-100 dark:bg-slate-800 px-1.5 py-0.5 rounded font-mono text-slate-700 dark:text-slate-300">X-Sequoia-Signature</code> header:</p>
                            <pre className="bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded p-3 text-xs font-mono text-slate-700 dark:text-slate-300 overflow-x-auto">
{`X-Sequoia-Signature: sha256=<hex_digest>

# Verify in Python:
import hmac, hashlib
expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
assert signature == f"sha256={expected}"`}
                            </pre>
                            <p>Webhooks retry up to 3 times with exponential backoff on failure. Use the test button in Settings to verify your endpoint.</p>
                        </div>
                    </div>
                </section>

                {/* Rate limits */}
                <section className="bg-white dark:bg-slate-900 rounded-lg border border-slate-200 dark:border-slate-700 overflow-hidden">
                    <div className="px-5 py-4 border-b border-slate-100 dark:border-slate-800">
                        <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-200">{t('apiHub.rateLimits')}</h2>
                    </div>
                    <div className="px-5 py-4">
                        <p className="text-xs text-slate-500 dark:text-slate-400 leading-relaxed">{t('apiHub.rateLimitsDescription')}</p>
                        <div className="mt-3 inline-flex items-center gap-2 bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded px-3 py-1.5">
                            <span className="text-sm font-mono font-semibold text-slate-700 dark:text-slate-300">{t('apiHub.requestsPerMinute', { count: 60 })}</span>
                        </div>
                    </div>
                </section>

                {/* Documentation link */}
                <section className="bg-white dark:bg-slate-900 rounded-lg border border-slate-200 dark:border-slate-700 px-5 py-4">
                    <div className="flex items-start gap-4">
                        <div className="w-10 h-10 rounded-lg bg-blue-50 dark:bg-blue-900 flex items-center justify-center flex-shrink-0">
                            <svg className="w-5 h-5 text-blue-500 dark:text-blue-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
                            </svg>
                        </div>
                        <div>
                            <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-200">{t('apiHub.docsLink')}</h3>
                            <p className="text-xs text-slate-400 dark:text-slate-500 mt-0.5">{t('apiHub.docsDescription')}</p>
                        </div>
                    </div>
                </section>

            </div>
        </div>
    )
}
