import { useState, useEffect } from 'react'
import { severityColor } from '../data'
import type { IncidentToast } from '../hooks/useUnseenIncidents'

interface Props {
  toasts: IncidentToast[]
  onClickToast: (incidentId: string, toastId: string) => void
}

const TOAST_LIFETIME = 10_000

export function IncidentToastStack({ toasts, onClickToast }: Props) {
  const [now, setNow] = useState(Date.now())

  // Tick every second to drive progress bar
  const hasToasts = toasts.length > 0
  useEffect(() => {
    if (!hasToasts) return
    const timer = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(timer)
  }, [hasToasts])

  if (toasts.length === 0) return null

  // Show up to 3 cards total (top + 2 peeking behind)
  const visibleStart = Math.max(0, toasts.length - 3)

  return (
    <div className="fixed bottom-4 left-4 z-50 pointer-events-auto" style={{ perspective: '600px' }}>
      <div className="relative" style={{ minWidth: 280 }}>
        {toasts.slice(visibleStart).map((toast, i) => {
          const stackPos = toasts.length - visibleStart - 1 - i // 0 = top, 1 = behind, 2 = furthest
          const scale = 1 - stackPos * 0.05
          const translateY = stackPos * 6
          const opacity = 1 - stackPos * 0.2
          const isTop = stackPos === 0
          const elapsed = now - toast.createdAt
          const progress = Math.max(0, 1 - elapsed / TOAST_LIFETIME)

          return (
            <div
              key={toast.id}
              className="absolute bottom-0 left-0 w-full"
              style={{
                transform: `scale(${scale}) translateY(${translateY}px)`,
                transformOrigin: 'bottom center',
                opacity,
                zIndex: 10 - stackPos,
                pointerEvents: isTop ? 'auto' : 'none',
                ...(stackPos === 0 ? { position: 'relative' } : {}),
                animation: isTop ? 'protoToastIn 200ms ease-out' : undefined,
              }}
            >
              <button
                onClick={() => onClickToast(toast.incidentId, toast.id)}
                className="w-full flex flex-col rounded-lg bg-[var(--proto-surface)] border border-[var(--proto-border)] shadow-lg cursor-pointer hover:bg-[var(--proto-surface-raised)] transition-colors text-left overflow-hidden"
              >
                <div className="flex items-start gap-2.5 px-3.5 py-2.5">
                  <span
                    className="shrink-0 w-2 h-2 rounded-full mt-1"
                    style={{ backgroundColor: severityColor[toast.severity as keyof typeof severityColor] }}
                  />
                  <div className="min-w-0 flex-1">
                    <div className="text-sm text-[var(--proto-text)] font-medium truncate max-w-[240px]">
                      {toast.title}
                    </div>
                    <div className="text-xs text-[var(--proto-text-muted)] mt-0.5">New {toast.type} detected</div>
                  </div>
                  {isTop && toasts.length > 1 && (
                    <span className="shrink-0 text-[10px] font-semibold text-[var(--proto-text-muted)] bg-[var(--proto-base)] rounded-full px-1.5 py-0.5 mt-0.5">
                      +{toasts.length - 1}
                    </span>
                  )}
                </div>
                {/* Progress bar */}
                <div className="w-full h-0.5 bg-[var(--proto-base)]">
                  <div
                    className="h-full bg-[var(--proto-accent)]"
                    style={{
                      width: `${progress * 100}%`,
                      transition: 'width 1s linear',
                    }}
                  />
                </div>
              </button>
            </div>
          )
        })}
      </div>
    </div>
  )
}
