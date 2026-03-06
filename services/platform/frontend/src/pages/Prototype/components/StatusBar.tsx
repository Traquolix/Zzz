import { useState, useEffect, useRef, type RefObject } from 'react'
import { Sparkline } from './Sparkline'

interface StatusBarProps {
  connected: boolean
  sectionCount: number
  incidentCount: number
  lastDetectionTsRef?: RefObject<number>
}

const PING_HISTORY_LENGTH = 30
const PING_INTERVAL_MS = 2000

export function StatusBar({ connected, sectionCount, incidentCount, lastDetectionTsRef }: StatusBarProps) {
  const [showTooltip, setShowTooltip] = useState(false)
  const [pingHistory, setPingHistory] = useState<number[]>([])
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    const measurePing = () => {
      const start = performance.now()
      fetch('/api/health', { method: 'HEAD', cache: 'no-store' })
        .then(() => {
          const ms = Math.round(performance.now() - start)
          setPingHistory(prev => [...prev.slice(-(PING_HISTORY_LENGTH - 1)), ms])
        })
        .catch(() => {
          setPingHistory(prev => [...prev.slice(-(PING_HISTORY_LENGTH - 1)), -1])
        })
    }

    measurePing()
    intervalRef.current = setInterval(measurePing, PING_INTERVAL_MS)
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [])

  const lastPing = pingHistory.length > 0 ? pingHistory[pingHistory.length - 1] : null
  const avgPing =
    pingHistory.filter(p => p > 0).length > 0
      ? Math.round(pingHistory.filter(p => p > 0).reduce((a, b) => a + b, 0) / pingHistory.filter(p => p > 0).length)
      : null

  const pingColor =
    lastPing === null
      ? 'var(--proto-text-muted)'
      : lastPing < 0
        ? 'var(--proto-red)'
        : lastPing < 100
          ? 'var(--proto-green)'
          : lastPing < 300
            ? 'var(--proto-amber)'
            : 'var(--proto-red)'

  return (
    <div className="absolute top-4 left-4 z-10 flex items-center gap-2.5">
      <span className="text-sm font-semibold text-[var(--proto-text)] tracking-tight">Sequoia Analytics</span>
      <div className="relative" onMouseEnter={() => setShowTooltip(true)} onMouseLeave={() => setShowTooltip(false)}>
        <span className="inline-flex items-center gap-1.5 text-[9px] font-medium px-1.5 py-0.5 rounded-full bg-[var(--proto-accent)]/20 text-[var(--proto-accent)] uppercase tracking-wider cursor-default relative -top-px">
          <span
            className={`w-1.5 h-1.5 rounded-full shrink-0 ${connected ? '' : 'animate-pulse'}`}
            style={{ backgroundColor: connected ? 'var(--proto-green)' : 'var(--proto-red)' }}
          />
          beta
        </span>
        {showTooltip && (
          <div className="absolute top-full left-1/2 -translate-x-1/2 mt-2 w-56 px-3 py-2.5 rounded-lg bg-[var(--proto-surface)] border border-[var(--proto-border)] shadow-lg text-xs z-50">
            <div className="flex flex-col gap-2">
              {/* Backend */}
              <div>
                <div className="flex items-center gap-1.5 mb-1">
                  <span
                    className={`w-1.5 h-1.5 rounded-full`}
                    style={{ backgroundColor: connected ? 'var(--proto-green)' : 'var(--proto-red)' }}
                  />
                  <span className="text-[var(--proto-text)] font-medium">Backend</span>
                  <span className="text-[var(--proto-text-muted)] ml-auto">
                    {connected ? 'Connected' : 'Disconnected'}
                  </span>
                </div>
                {pingHistory.filter(p => p > 0).length > 0 && (
                  <div className="flex items-center gap-2">
                    <div className="flex-1 overflow-hidden">
                      <Sparkline data={pingHistory.filter(p => p > 0)} color={pingColor} width={120} height={20} />
                    </div>
                    <span className="text-[var(--proto-text-muted)] shrink-0 tabular-nums">
                      {lastPing != null && lastPing > 0 ? `${lastPing}ms` : '—'}
                    </span>
                  </div>
                )}
                {avgPing != null && <div className="text-[var(--proto-text-muted)]/60 mt-0.5">avg {avgPing}ms</div>}
              </div>

              <div className="w-full h-px bg-[var(--proto-border)]" />

              {/* Frontend */}
              <div>
                <div className="flex items-center gap-1.5">
                  <span className="w-1.5 h-1.5 rounded-full bg-[var(--proto-green)]" />
                  <span className="text-[var(--proto-text)] font-medium">Frontend</span>
                  <span className="text-[var(--proto-text-muted)] ml-auto">Running</span>
                </div>
                <div className="text-[var(--proto-text-muted)] mt-0.5">
                  {sectionCount} section{sectionCount !== 1 ? 's' : ''} · {incidentCount} incident
                  {incidentCount !== 1 ? 's' : ''}
                </div>
              </div>

              {lastDetectionTsRef?.current ? (
                <>
                  <div className="w-full h-px bg-[var(--proto-border)]" />
                  <div>
                    <div className="flex items-center gap-1.5">
                      <span className="w-1.5 h-1.5 rounded-full bg-[var(--proto-accent)]" />
                      <span className="text-[var(--proto-text)] font-medium">Last detection</span>
                    </div>
                    <div className="text-[var(--proto-text-muted)] mt-0.5 tabular-nums">
                      {new Date(lastDetectionTsRef.current).toLocaleTimeString()}{' '}
                      <span className="opacity-60">
                        (data delay: ~{Math.round((Date.now() - lastDetectionTsRef.current) / 1000)}s)
                      </span>
                    </div>
                  </div>
                </>
              ) : null}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
