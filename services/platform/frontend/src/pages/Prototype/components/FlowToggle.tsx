import { cn } from '@/lib/utils'
import type { DataFlow } from '@/context/RealtimeContext'

interface FlowToggleProps {
  flow: DataFlow
  availableFlows: DataFlow[]
  onToggle: (flow: DataFlow) => void
}

const labels: Record<DataFlow, string> = { live: 'Live', sim: 'Sim' }

export function FlowToggle({ flow, availableFlows, onToggle }: FlowToggleProps) {
  const options: DataFlow[] = ['live', 'sim']

  return (
    <div className="inline-flex rounded-md bg-[var(--proto-surface)] border border-[var(--proto-border)] p-0.5 gap-0.5">
      {options.map(opt => {
        const active = flow === opt
        const disabled = !availableFlows.includes(opt)
        return (
          <button
            key={opt}
            onClick={() => !disabled && onToggle(opt)}
            disabled={disabled}
            title={disabled ? `${labels[opt]} data source unavailable` : `Switch to ${labels[opt]} data`}
            className={cn(
              'px-2.5 py-0.5 text-[11px] font-medium rounded transition-colors cursor-pointer',
              active && 'bg-[var(--proto-surface-raised)] text-[var(--proto-text)]',
              !active && !disabled && 'text-[var(--proto-text-secondary)] hover:text-[var(--proto-text)]',
              disabled && 'text-[var(--proto-text-muted)] opacity-40 cursor-not-allowed',
            )}
          >
            {opt === 'live' && (
              <span
                className={cn(
                  'inline-block w-1.5 h-1.5 rounded-full mr-1 align-middle',
                  active ? 'bg-green-400' : disabled ? 'bg-gray-500' : 'bg-gray-400',
                )}
              />
            )}
            {labels[opt]}
          </button>
        )
      })}
    </div>
  )
}
