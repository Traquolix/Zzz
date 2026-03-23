import { useState, type RefObject } from 'react'
import { COLORS } from '@/lib/theme'
import { cn } from '@/lib/utils'
import { fibers } from '../data'
import { useWaterfallBuffer } from '../hooks/useWaterfallBuffer'
import type { WaterfallDot } from '../hooks/useWaterfallBuffer'
import { WaterfallCanvas } from './WaterfallCanvas'

export function WaterfallPanel() {
  // NOTE: index-based selection assumes `fibers` is a static array.
  // If fibers become dynamic (TTL/hot-reload), switch to keying by fiber ID.
  const [selectedIndex, setSelectedIndex] = useState(0)
  const [windowMs, setWindowMs] = useState(120_000)

  const fiber = fibers[selectedIndex] ?? fibers[0]
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
      <div className="flex items-center gap-2 px-4 py-2 border-b border-[var(--proto-border)]">
        <select
          value={selectedIndex}
          onChange={e => setSelectedIndex(Number(e.target.value))}
          className="text-cq-xs px-2 py-1 rounded bg-[var(--proto-base)] border border-[var(--proto-border)] text-[var(--proto-text)] outline-none"
        >
          {fibers.map((f, i) => (
            <option key={f.id} value={i}>
              {f.name}:{f.direction}
            </option>
          ))}
        </select>
        <div className="flex rounded overflow-hidden border border-[var(--proto-border)]">
          {[60_000, 120_000].map(ms => (
            <button
              key={ms}
              onClick={() => setWindowMs(ms)}
              className={cn(
                'text-cq-xs px-2 py-1 transition-colors cursor-pointer',
                windowMs === ms
                  ? 'bg-[var(--proto-accent)] text-white'
                  : 'bg-[var(--proto-base)] text-[var(--proto-text-muted)] hover:text-[var(--proto-text)]',
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
          dotsRef={dotsRef as unknown as RefObject<WaterfallDot[]>}
          dirtyRef={dirtyRef}
          lastTsRef={lastTsRef as unknown as RefObject<number>}
          prune={prune}
          windowMs={windowMs}
          minChannel={minChannel}
          maxChannel={maxChannel}
        />
      </div>

      {/* Speed color legend */}
      <div className="flex items-center gap-3 px-4 py-2 border-t border-[var(--proto-border)]">
        <span className="text-cq-2xs text-[var(--proto-text-muted)]">Speed:</span>
        {[
          { color: COLORS.speed.fast, label: '≥80' },
          { color: COLORS.speed.normal, label: '≥60' },
          { color: COLORS.speed.slow, label: '≥30' },
          { color: COLORS.speed.stopped, label: '<30' },
        ].map(({ color, label }) => (
          <div key={label} className="flex items-center gap-1">
            <span className="w-2.5 h-2.5 rounded-sm" style={{ backgroundColor: color }} />
            <span className="text-cq-2xs text-[var(--proto-text-muted)]">{label}</span>
          </div>
        ))}
        <span className="text-cq-2xs text-[var(--proto-text-muted)] ml-auto">km/h</span>
      </div>
    </div>
  )
}
