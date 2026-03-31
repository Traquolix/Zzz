import { useState } from 'react'
import { COLORS } from '@/lib/theme'
import { cn } from '@/lib/utils'
import { useFiberData } from '../context/FiberContext'
import { useWaterfallBuffer } from '../hooks/useWaterfallBuffer'
import { WaterfallCanvas } from './WaterfallCanvas'

export function WaterfallPanel() {
  const { fibers } = useFiberData()
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [windowMs, setWindowMs] = useState(120_000)

  const fiber = fibers.find(f => f.id === selectedId) ?? fibers[0]
  const minChannel = 0
  const maxChannel = (fiber?.totalChannels ?? 500) - 1

  const { dotsRef, dirtyRef, prune, lastTsRef } = useWaterfallBuffer(
    fiber?.parentCableId ?? '',
    fiber?.direction ?? 0,
    windowMs,
  )

  return (
    <div className="flex flex-col h-full">
      {/* Controls */}
      <div className="flex items-center gap-2 px-4 py-2 border-b border-[var(--dash-border)]">
        <select
          value={fiber?.id ?? ''}
          onChange={e => setSelectedId(e.target.value)}
          className="text-cq-xs px-2 py-1 rounded bg-[var(--dash-base)] border border-[var(--dash-border)] text-[var(--dash-text)] outline-none"
        >
          {fibers.map(f => (
            <option key={f.id} value={f.id}>
              {f.name}:{f.direction}
            </option>
          ))}
        </select>
        <div className="flex rounded overflow-hidden border border-[var(--dash-border)]">
          {[60_000, 120_000].map(ms => (
            <button
              key={ms}
              onClick={() => setWindowMs(ms)}
              className={cn(
                'text-cq-xs px-2 py-1 transition-colors cursor-pointer',
                windowMs === ms
                  ? 'bg-[var(--dash-accent)] text-white'
                  : 'bg-[var(--dash-base)] text-[var(--dash-text-muted)] hover:text-[var(--dash-text)]',
              )}
            >
              {ms / 1000}s
            </button>
          ))}
        </div>
      </div>

      {/* Canvas */}
      <div className="flex-1 min-h-0 p-2">
        <WaterfallCanvas
          dotsRef={dotsRef}
          dirtyRef={dirtyRef}
          lastTsRef={lastTsRef}
          prune={prune}
          windowMs={windowMs}
          minChannel={minChannel}
          maxChannel={maxChannel}
        />
      </div>

      {/* Speed color legend */}
      <div className="flex items-center gap-3 px-4 py-2 border-t border-[var(--dash-border)]">
        <span className="text-cq-2xs text-[var(--dash-text-muted)]">Speed:</span>
        {[
          { color: COLORS.speed.fast, label: '≥80' },
          { color: COLORS.speed.normal, label: '≥60' },
          { color: COLORS.speed.slow, label: '≥30' },
          { color: COLORS.speed.stopped, label: '<30' },
        ].map(({ color, label }) => (
          <div key={label} className="flex items-center gap-1">
            <span className="w-2.5 h-2.5 rounded-sm" style={{ backgroundColor: color }} />
            <span className="text-cq-2xs text-[var(--dash-text-muted)]">{label}</span>
          </div>
        ))}
        <span className="text-cq-2xs text-[var(--dash-text-muted)] ml-auto">km/h</span>
      </div>
    </div>
  )
}
