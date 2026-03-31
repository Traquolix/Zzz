/**
 * Generic segmented-control toggle — shared across DataExportPanel,
 * SidePanel, and any future pill-toggle UI.
 */

interface ToggleGroupProps<T extends string> {
  options: T[]
  value: T
  onChange: (v: T) => void
  labels: Record<T, string>
}

export function ToggleGroup<T extends string>({ options, value, onChange, labels }: ToggleGroupProps<T>) {
  return (
    <div className="inline-flex rounded-md bg-[var(--dash-surface)] border border-[var(--dash-border)] p-0.5 gap-0.5">
      {options.map(opt => (
        <button
          key={opt}
          onClick={() => onChange(opt)}
          className={`px-2.5 py-1 rounded text-cq-xxs font-medium transition-colors cursor-pointer whitespace-nowrap ${
            value === opt
              ? 'bg-[var(--dash-surface-raised)] text-[var(--dash-text)]'
              : 'text-[var(--dash-text-secondary)] hover:text-[var(--dash-text)]'
          }`}
        >
          {labels[opt]}
        </button>
      ))}
    </div>
  )
}
