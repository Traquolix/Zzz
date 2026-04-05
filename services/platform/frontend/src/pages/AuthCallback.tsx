import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { getUserManager } from '@/auth/oidc'

export function AuthCallback() {
  const navigate = useNavigate()
  const [error, setError] = useState<string | null>(null)
  const { t } = useTranslation()

  useEffect(() => {
    const processCallback = async () => {
      try {
        const mgr = await getUserManager()
        await mgr.signinRedirectCallback()
        navigate('/', { replace: true })
      } catch (e) {
        setError(e instanceof Error ? e.message : t('auth.connectionFailed'))
      }
    }
    processCallback()
  }, [navigate, t])

  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="text-center">
          <p className="text-red-500 mb-4">{error}</p>
          <a href="/login" className="text-blue-500 underline">
            {t('auth.backToLogin')}
          </a>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-background">
      <div className="text-foreground/50">{t('auth.authenticating')}</div>
    </div>
  )
}
