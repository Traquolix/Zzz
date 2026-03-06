import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { useAuth } from '@/hooks/useAuth'
import { Button } from '@/components/ui/button'
import { FormField } from '@/components/ui/form-field'

export function Login() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [touched, setTouched] = useState<Record<string, boolean>>({})

  const { login } = useAuth()
  const navigate = useNavigate()
  const { t } = useTranslation()

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    setIsSubmitting(true)

    const result = await login(username, password)

    if (result.success) {
      toast.success(t('auth.welcomeBack', { username }))
      navigate('/')
    } else {
      setError(result.error || t('auth.loginFailed'))
    }

    setIsSubmitting(false)
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-background">
      <div className="w-full max-w-sm">
        <div className="bg-white rounded-lg shadow-lg p-8">
          <div className="text-center mb-8">
            <h1 className="text-2xl font-bold text-slate-900">{t('common.appName')}</h1>
            <p className="text-sm text-slate-500 mt-1">{t('common.appTagline')}</p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            {error && (
              <div role="alert" className="text-sm text-red-600 bg-red-50 px-3 py-2 rounded-md">
                {error}
              </div>
            )}

            <FormField
              id="username"
              label={t('auth.username')}
              type="text"
              value={username}
              onChange={e => setUsername(e.target.value)}
              onBlur={() => setTouched(prev => ({ ...prev, username: true }))}
              required
              autoComplete="username"
              autoFocus
              touched={touched.username}
              error={!username ? t('auth.username') + ' ' + t('common.required') : undefined}
            />

            <FormField
              id="password"
              label={t('auth.password')}
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              onBlur={() => setTouched(prev => ({ ...prev, password: true }))}
              required
              autoComplete="current-password"
              touched={touched.password}
              error={!password ? t('auth.password') + ' ' + t('common.required') : undefined}
            />

            <Button type="submit" className="w-full" isLoading={isSubmitting} loadingText={t('auth.signingIn')}>
              {t('auth.loginButton')}
            </Button>
          </form>
        </div>
      </div>
    </div>
  )
}
