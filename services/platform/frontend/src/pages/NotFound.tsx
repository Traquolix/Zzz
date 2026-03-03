import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'

export function NotFound() {
    const { t } = useTranslation()

    return (
        <div className="min-h-screen flex items-center justify-center bg-background">
            <div className="text-center">
                <h1 className="text-8xl font-bold text-slate-300">404</h1>
                <h2 className="text-2xl font-semibold text-slate-700 mt-4">{t('notFound.title')}</h2>
                <p className="text-slate-500 mt-2 max-w-md">
                    {t('notFound.description')}
                </p>
                <Button asChild className="mt-6">
                    <Link to="/">{t('notFound.backLink')}</Link>
                </Button>
            </div>
        </div>
    )
}
