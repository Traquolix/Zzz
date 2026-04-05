import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import { getUserManager } from '@/auth/oidc'

export function Login() {
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const { t } = useTranslation()

  const handleSignIn = async () => {
    setIsLoading(true)
    setError(null)
    try {
      const mgr = await getUserManager()
      await mgr.signinRedirect()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to start login')
      setIsLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-background">
      <div className="w-full max-w-sm">
        <div className="bg-white rounded-lg shadow-lg p-8">
          <div className="text-center mb-8">
            <h1 className="text-2xl font-bold text-slate-900">{t('common.appName')}</h1>
            <p className="text-sm text-slate-500 mt-1">{t('common.appTagline')}</p>
          </div>

          {error && (
            <div role="alert" className="text-sm text-red-600 bg-red-50 px-3 py-2 rounded-md mb-4">
              {error}
            </div>
          )}

          <Button onClick={handleSignIn} className="w-full" isLoading={isLoading} loadingText={t('auth.signingIn')}>
            {t('auth.loginButton')}
          </Button>
        </div>
      </div>
    </div>
  )
}
