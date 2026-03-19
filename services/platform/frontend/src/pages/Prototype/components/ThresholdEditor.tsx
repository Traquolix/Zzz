import { useState, useEffect } from 'react'
import { COLORS } from '@/lib/theme'
import type { SpeedThresholds } from '../types'

export function ThresholdEditor({
  thresholds,
  onChange,
}: {
  thresholds: SpeedThresholds
  onChange: (t: SpeedThresholds) => void
}) {
  const [draft, setDraft] = useState<SpeedThresholds>(thresholds)
  const isDirty =
    draft.green !== thresholds.green || draft.yellow !== thresholds.yellow || draft.orange !== thresholds.orange

  // Sync draft when thresholds change externally (e.g. switching sections)
  useEffect(() => {
    setDraft(thresholds)
    // eslint-disable-next-line react-hooks/exhaustive-deps -- list individual fields to avoid re-render when object ref changes but values are the same
  }, [thresholds.green, thresholds.yellow, thresholds.orange])

  const fields: { key: keyof SpeedThresholds; label: string; color: string }[] = [
    { key: 'green', label: 'Green', color: COLORS.speed.fast },
    { key: 'yellow', label: 'Yellow', color: COLORS.speed.normal },
    { key: 'orange', label: 'Orange', color: COLORS.speed.slow },
  ]

  return (
    <div className="border-t border-[var(--proto-border)] pt-3">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-cq-xs font-medium text-[var(--proto-text-muted)] uppercase tracking-wider">
          Speed Thresholds
        </h3>
        {isDirty && (
          <button
            onClick={() => onChange(draft)}
            className="px-2.5 py-1 rounded text-cq-2xs font-medium bg-[var(--proto-accent)] text-white cursor-pointer hover:opacity-80 transition-opacity"
          >
            Apply
          </button>
        )}
      </div>
      <div className="flex gap-5">
        {fields.map(f => (
          <label key={f.key} className="flex items-center gap-2">
            <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ backgroundColor: f.color }} />
            <input
              type="number"
              value={draft[f.key]}
              onChange={e => {
                const val = parseInt(e.target.value, 10)
                if (!isNaN(val) && val >= 0) {
                  setDraft(prev => ({ ...prev, [f.key]: val }))
                }
              }}
              className="w-12 px-1 py-0.5 rounded bg-transparent border border-[var(--proto-border)] text-cq-xs text-[var(--proto-text)] text-center outline-none focus:border-[var(--proto-text-secondary)] [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
            />
            <span className="text-cq-2xs text-[var(--proto-text-muted)]">km/h</span>
          </label>
        ))}
      </div>
    </div>
  )
}
