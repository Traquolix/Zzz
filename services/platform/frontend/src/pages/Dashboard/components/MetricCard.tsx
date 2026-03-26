import { cn } from '@/lib/utils'

export function MetricCard({
  label,
  value,
  unit,
  valueColor,
  labelExtra,
  children,
  compact,
}: {
  label: string
  value: string | number
  unit?: string
  valueColor?: string
  labelExtra?: React.ReactNode
  children?: React.ReactNode
  compact?: boolean
}) {
  return (
    <div className={cn('rounded-lg border border-[var(--dash-border)]', compact ? 'p-2.5' : 'p-3')}>
      <div
        className={cn(
          'text-cq-2xs text-[var(--dash-text-muted)] uppercase tracking-wider',
          compact ? 'mb-0.5' : 'mb-1',
        )}
      >
        {label}
        {labelExtra}
      </div>
      <div className="flex items-end justify-between">
        <div>
          <span
            className={cn('font-semibold', compact ? 'text-cq-lg' : 'text-cq-xl')}
            style={{ color: valueColor ?? 'var(--dash-text)' }}
          >
            {value}
          </span>
          {unit && (
            <span className={cn('text-[var(--dash-text-muted)]', compact ? 'text-cq-2xs ml-0.5' : 'text-cq-xs ml-1')}>
              {unit}
            </span>
          )}
        </div>
        {children}
      </div>
    </div>
  )
}
