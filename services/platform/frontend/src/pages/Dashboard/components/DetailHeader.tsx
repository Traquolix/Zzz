import { useTranslation } from 'react-i18next'

export function DetailHeader({
  title,
  subtitle,
  onBack,
  badge,
}: {
  title: React.ReactNode
  subtitle?: React.ReactNode
  onBack?: () => void
  badge?: React.ReactNode
}) {
  const { t } = useTranslation()

  return (
    <div className="sticky top-0 z-10 bg-[var(--dash-surface)] border-b border-[var(--dash-border)] px-4 py-3 flex items-center gap-3">
      {onBack && (
        <button
          onClick={onBack}
          className="text-[var(--dash-text-muted)] hover:text-[var(--dash-text)] transition-colors text-cq-sm cursor-pointer"
        >
          &larr; {t('common.back')}
        </button>
      )}
      <div className="min-w-0">
        <span className="text-cq-sm font-semibold text-[var(--dash-text)] truncate block">{title}</span>
        {subtitle}
      </div>
      {badge}
    </div>
  )
}
