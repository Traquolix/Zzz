import { useState, useMemo, useEffect, useLayoutEffect, useRef } from 'react'
import { createPortal } from 'react-dom'
import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'
import { COLORS } from '@/lib/theme'
import { fibers, defaultSpeedThresholds, getFiberColor } from '../data'
import type { Fiber, MapPageAction, SpeedThresholds } from '../types'
import { FlowToggle } from './FlowToggle'
import { ThresholdEditor } from './ThresholdEditor'
import type { DataFlow } from '@/context/RealtimeContext'

// ── Settings panel ──────────────────────────────────────────────────────

function ColorPicker({
  current,
  onSelect,
  onClose,
  anchorRef,
}: {
  current: string
  onSelect: (c: string) => void
  onClose: () => void
  anchorRef?: React.RefObject<HTMLElement | null>
}) {
  const ref = useRef<HTMLDivElement>(null)
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null)
  const readyRef = useRef(false)

  useLayoutEffect(() => {
    if (!anchorRef?.current) return
    const rect = anchorRef.current.getBoundingClientRect()
    const pickerHeight = 4 * (20 + 6) + 16
    let top = rect.top - pickerHeight - 8
    if (top < 8) top = rect.bottom + 8
    setPos({ top, left: rect.left })
  }, [anchorRef])

  // Mark ready after a frame so the opening click doesn't immediately close
  useEffect(() => {
    const id = requestAnimationFrame(() => {
      readyRef.current = true
    })
    return () => cancelAnimationFrame(id)
  }, [])

  useEffect(() => {
    function handler(e: MouseEvent) {
      if (!readyRef.current) return
      if (ref.current && !ref.current.contains(e.target as Node)) {
        onClose()
      }
    }
    document.addEventListener('mousedown', handler, true)
    return () => document.removeEventListener('mousedown', handler, true)
  }, [onClose])

  if (!pos) return null

  return createPortal(
    <div ref={ref} className="dashboard" style={{ position: 'fixed', zIndex: 9999, top: pos.top, left: pos.left }}>
      <div className="p-2 rounded-lg bg-[var(--dash-surface-raised)] border border-[var(--dash-border)] shadow-xl grid grid-cols-6 gap-1.5">
        {COLORS.fiber.palette.map(c => (
          <button
            key={c}
            onClick={() => {
              onSelect(c)
              onClose()
            }}
            className={cn(
              'w-5 h-5 rounded-full cursor-pointer transition-transform hover:scale-125',
              c === current && 'ring-2 ring-white ring-offset-1 ring-offset-[var(--dash-surface-raised)]',
            )}
            style={{ backgroundColor: c }}
          />
        ))}
      </div>
    </div>,
    document.body,
  )
}

function FiberColorDot({
  direction,
  color,
  isPickerOpen,
  onTogglePicker,
  onSelect,
  onClosePicker,
  onMouseEnter,
  onMouseLeave,
}: {
  direction: 0 | 1
  color: string
  isPickerOpen: boolean
  onTogglePicker: () => void
  onSelect: (c: string) => void
  onClosePicker: () => void
  onMouseEnter: () => void
  onMouseLeave: () => void
}) {
  const btnRef = useRef<HTMLButtonElement>(null)
  const dirLabel = direction === 0 ? 'Dir A' : 'Dir B'

  return (
    <div className="flex items-center gap-1.5" onMouseEnter={onMouseEnter} onMouseLeave={onMouseLeave}>
      <button
        ref={btnRef}
        onClick={onTogglePicker}
        className="w-3 h-3 rounded-full shrink-0 cursor-pointer ring-offset-1 ring-offset-[var(--dash-surface)] hover:ring-1 hover:ring-[var(--dash-text-muted)] transition-all"
        style={{ backgroundColor: color }}
        title={`Change ${dirLabel} color`}
      />
      <span className="text-cq-2xs text-[var(--dash-text-muted)]">{dirLabel}</span>
      {isPickerOpen && <ColorPicker current={color} onSelect={onSelect} onClose={onClosePicker} anchorRef={btnRef} />}
    </div>
  )
}

function SettingsPanel({
  fiberThresholds,
  fiberColors,
  dispatch,
  onHighlightFiber,
  onClearHighlight,
  show3DBuildings,
  showChannelHelper,
  showFullCable,
  flow,
  switchingFlow,
  availableFlows,
  onFlowToggle,
}: {
  fiberThresholds: Record<string, SpeedThresholds>
  fiberColors: Record<string, string>
  dispatch: React.Dispatch<MapPageAction>
  onHighlightFiber?: (fiberId: string) => void
  onClearHighlight?: () => void
  show3DBuildings: boolean
  showChannelHelper: boolean
  showFullCable: boolean
  flow: DataFlow
  switchingFlow: boolean
  availableFlows: DataFlow[]
  onFlowToggle: (flow: DataFlow) => void
}) {
  const { t } = useTranslation()
  const [colorPickerOpen, setColorPickerOpen] = useState<string | null>(null)

  // Group fibers by cable
  const cableGroups = useMemo(() => {
    const map = new Map<string, { name: string; fibers: Fiber[] }>()
    for (const f of fibers) {
      let group = map.get(f.parentCableId)
      if (!group) {
        group = { name: f.name, fibers: [] }
        map.set(f.parentCableId, group)
      }
      group.fibers.push(f)
    }
    return [...map.entries()]
  }, [])

  return (
    <div className="px-4 py-4 flex flex-col gap-5">
      {/* Data source */}
      <div className="flex flex-col gap-2">
        <span className="text-cq-xs text-[var(--dash-text-secondary)]">{t('flow.label')}</span>
        <FlowToggle flow={flow} switchingFlow={switchingFlow} availableFlows={availableFlows} onToggle={onFlowToggle} />
      </div>

      <div className="h-px bg-[var(--dash-border)]" />

      {/* Map display toggles */}
      <div className="flex flex-col gap-2">
        <span className="text-cq-xs text-[var(--dash-text-secondary)]">Map</span>
        <label className="flex items-center justify-between cursor-pointer group">
          <span className="text-cq-sm text-[var(--dash-text)]">3D Buildings</span>
          <button
            onClick={() => dispatch({ type: 'TOGGLE_3D_BUILDINGS' })}
            className={`relative w-8 h-[18px] rounded-full transition-colors ${show3DBuildings ? 'bg-[var(--dash-accent)]' : 'bg-[var(--dash-border)]'}`}
          >
            <span
              className={`absolute top-[2px] left-[2px] w-[14px] h-[14px] rounded-full bg-white transition-transform ${show3DBuildings ? 'translate-x-[14px]' : ''}`}
            />
          </button>
        </label>
        <label className="flex items-center justify-between cursor-pointer group">
          <span className="text-cq-sm text-[var(--dash-text)]">Channel Helper</span>
          <button
            onClick={() => dispatch({ type: 'TOGGLE_CHANNEL_HELPER' })}
            className={`relative w-8 h-[18px] rounded-full transition-colors ${showChannelHelper ? 'bg-[var(--dash-accent)]' : 'bg-[var(--dash-border)]'}`}
          >
            <span
              className={`absolute top-[2px] left-[2px] w-[14px] h-[14px] rounded-full bg-white transition-transform ${showChannelHelper ? 'translate-x-[14px]' : ''}`}
            />
          </button>
        </label>
        <label className="flex items-center justify-between cursor-pointer group">
          <span className="text-cq-sm text-[var(--dash-text)]">Show Full Cable</span>
          <button
            onClick={() => dispatch({ type: 'TOGGLE_SHOW_FULL_CABLE' })}
            className={`relative w-8 h-[18px] rounded-full transition-colors ${showFullCable ? 'bg-[var(--dash-accent)]' : 'bg-[var(--dash-border)]'}`}
          >
            <span
              className={`absolute top-[2px] left-[2px] w-[14px] h-[14px] rounded-full bg-white transition-transform ${showFullCable ? 'translate-x-[14px]' : ''}`}
            />
          </button>
        </label>
      </div>

      <div className="h-px bg-[var(--dash-border)]" />

      <div className="text-cq-xs text-[var(--dash-text-secondary)]">
        Default speed thresholds per fiber. Sections inherit these unless overridden.
      </div>
      {cableGroups.map(([cableId, group]) => {
        const current = fiberThresholds[group.fibers[0].id] ?? defaultSpeedThresholds

        return (
          <div key={cableId} className="flex flex-col gap-2">
            <div className="flex items-center gap-2">
              <span className="text-cq-sm font-medium text-[var(--dash-text)]">{group.name}</span>
            </div>
            {/* Per-direction color dots */}
            <div className="flex gap-4 pl-0.5">
              {group.fibers.map(f => (
                <FiberColorDot
                  key={f.id}
                  direction={f.direction}
                  color={getFiberColor(f, fiberColors)}
                  isPickerOpen={colorPickerOpen === f.id}
                  onTogglePicker={() => setColorPickerOpen(colorPickerOpen === f.id ? null : f.id)}
                  onSelect={c => dispatch({ type: 'SET_FIBER_COLOR', fiberId: f.id, color: c })}
                  onClosePicker={() => setColorPickerOpen(null)}
                  onMouseEnter={() => onHighlightFiber?.(f.id)}
                  onMouseLeave={() => onClearHighlight?.()}
                />
              ))}
            </div>
            <ThresholdEditor
              thresholds={current}
              onChange={t => {
                for (const f of group.fibers) {
                  dispatch({ type: 'SET_FIBER_THRESHOLDS', fiberId: f.id, thresholds: t })
                }
              }}
            />
          </div>
        )
      })}
    </div>
  )
}

export { SettingsPanel }
