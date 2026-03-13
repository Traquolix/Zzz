import { useState, useEffect, useRef, useMemo, type RefObject } from 'react'
import { useQuery } from '@tanstack/react-query'
import { API_URL } from '@/constants/api'
import { Sparkline } from './Sparkline'

interface StatusBarProps {
  connected: boolean
  sectionCount: number
  incidentCount: number
  lastDetectionTsRef?: RefObject<number>
}

const PING_HISTORY_LENGTH = 30
const PING_INTERVAL_MS = 2000
const READINESS_INTERVAL_MS = 10_000

interface ReadinessResponse {
  status: 'ready' | 'degraded'
  checks: Record<string, string>
}

const SERVICE_LABELS: Record<string, string> = {
  database: 'Database',
  clickhouse: 'Analytics DB',
  cache: 'Cache',
  kafka: 'Message broker',
  simulation: 'Simulation',
}

function statusColor(status: string): string {
  if (status === 'ok' || status === 'running') return 'var(--proto-green)'
  if (status === 'idle' || status === 'not_configured') return 'var(--proto-text-muted)'
  if (status === 'unknown') return 'var(--proto-amber)'
  return 'var(--proto-red)'
}

function statusLabel(status: string): string {
  if (status === 'ok' || status === 'running') return 'ok'
  if (status === 'not_configured') return 'n/a'
  return status
}

export function StatusBar({ connected, sectionCount, incidentCount, lastDetectionTsRef }: StatusBarProps) {
  const [showTooltip, setShowTooltip] = useState(false)
  const [shiftHeld, setShiftHeld] = useState(false)
  const pingHistoryRef = useRef<number[]>([])
  const [pingHistory, setPingHistory] = useState<number[]>([])

  // Track shift key for expanded tooltip
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => setShiftHeld(e.shiftKey)
    window.addEventListener('keydown', onKey)
    window.addEventListener('keyup', onKey)
    return () => {
      window.removeEventListener('keydown', onKey)
      window.removeEventListener('keyup', onKey)
    }
  }, [])

  // React Query handles refetch interval and automatic pause on hidden tabs
  const { data: lastPingResult, dataUpdatedAt } = useQuery({
    queryKey: ['ping'],
    queryFn: async () => {
      const start = performance.now()
      try {
        await fetch(`${API_URL}/api/health`, { method: 'HEAD', cache: 'no-store' })
        return Math.round(performance.now() - start)
      } catch {
        return -1
      }
    },
    refetchInterval: PING_INTERVAL_MS,
    staleTime: 0,
  })

  useEffect(() => {
    if (lastPingResult == null) return
    const next = [...pingHistoryRef.current.slice(-(PING_HISTORY_LENGTH - 1)), lastPingResult]
    pingHistoryRef.current = next
    setPingHistory(next)
  }, [lastPingResult, dataUpdatedAt])

  const lastPing = pingHistory.length > 0 ? pingHistory[pingHistory.length - 1] : null
  const positivePings = useMemo(() => pingHistory.filter(p => p > 0), [pingHistory])
  const avgPing =
    positivePings.length > 0 ? Math.round(positivePings.reduce((a, b) => a + b, 0) / positivePings.length) : null

  const { data: readiness } = useQuery<ReadinessResponse>({
    queryKey: ['readiness'],
    queryFn: async () => {
      const res = await fetch(`${API_URL}/api/health/ready`, { cache: 'no-store' })
      return res.json() as Promise<ReadinessResponse>
    },
    refetchInterval: READINESS_INTERVAL_MS,
    staleTime: 0,
    retry: false,
  })

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

  // Overall health: green if connected + ready, amber if degraded, red if disconnected
  const infraReady = !readiness || readiness.status === 'ready'
  const overallColor = !connected ? 'var(--proto-red)' : infraReady ? 'var(--proto-green)' : 'var(--proto-amber)'
  const overallLabel = !connected ? 'Disconnected' : infraReady ? 'All systems operational' : 'Degraded'

  const detectionAge =
    lastDetectionTsRef?.current != null ? Math.round((Date.now() - lastDetectionTsRef.current) / 1000) : null

  const expanded = showTooltip && shiftHeld

  return (
    <div className="absolute top-4 left-4 z-10 flex items-center gap-2.5">
      <span className="text-sm font-semibold text-[var(--proto-text)] tracking-tight">Sequoia Analytics</span>
      <div className="relative" onMouseEnter={() => setShowTooltip(true)} onMouseLeave={() => setShowTooltip(false)}>
        <span className="inline-flex items-center gap-1.5 text-[9px] font-medium px-1.5 py-0.5 rounded-full bg-[var(--proto-accent)]/20 text-[var(--proto-accent)] uppercase tracking-wider cursor-default relative -top-px">
          <span
            className={`w-1.5 h-1.5 rounded-full shrink-0 ${!connected ? 'animate-pulse' : ''}`}
            style={{ backgroundColor: overallColor }}
          />
          beta
        </span>
        {showTooltip && (
          <div className="absolute top-full left-1/2 -translate-x-1/2 mt-2 w-56 px-3 py-2.5 rounded-lg bg-[var(--proto-surface)] border border-[var(--proto-border)] shadow-lg text-xs z-50">
            <div className="flex flex-col gap-2">
              {/* Overall status */}
              <div className="flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ backgroundColor: overallColor }} />
                <span className="text-[var(--proto-text)] font-medium">{overallLabel}</span>
              </div>

              {/* Ping sparkline */}
              {positivePings.length > 0 && (
                <div className="flex items-center gap-2">
                  <div className="flex-1 overflow-hidden">
                    <Sparkline data={positivePings} color={pingColor} width={120} height={20} />
                  </div>
                  <span className="text-[var(--proto-text-muted)] shrink-0 tabular-nums">
                    {lastPing != null && lastPing > 0 ? `${lastPing}ms` : '—'}
                  </span>
                </div>
              )}

              {/* Stats line */}
              <div className="text-[var(--proto-text-muted)]">
                {sectionCount} section{sectionCount !== 1 ? 's' : ''} · {incidentCount} incident
                {incidentCount !== 1 ? 's' : ''}
                {detectionAge != null && <span className="opacity-60"> · last data ~{detectionAge}s ago</span>}
              </div>

              {/* Expanded: per-service breakdown (shift+hover) */}
              {expanded && (
                <>
                  <div className="w-full h-px bg-[var(--proto-border)]" />

                  <div className="flex flex-col gap-1">
                    {/* Backend */}
                    <div className="flex items-center gap-1.5">
                      <span
                        className="w-1.5 h-1.5 rounded-full shrink-0"
                        style={{ backgroundColor: connected ? 'var(--proto-green)' : 'var(--proto-red)' }}
                      />
                      <span className="text-[var(--proto-text-muted)]">Backend</span>
                      <span className="text-[var(--proto-text-muted)]/60 ml-auto">
                        {connected ? 'ok' : 'disconnected'}
                      </span>
                    </div>

                    {/* Infrastructure services */}
                    {readiness &&
                      Object.entries(readiness.checks).map(([key, status]) => (
                        <div key={key} className="flex items-center gap-1.5">
                          <span
                            className="w-1.5 h-1.5 rounded-full shrink-0"
                            style={{ backgroundColor: statusColor(status) }}
                          />
                          <span className="text-[var(--proto-text-muted)]">{SERVICE_LABELS[key] ?? key}</span>
                          <span className="text-[var(--proto-text-muted)]/60 ml-auto">{statusLabel(status)}</span>
                        </div>
                      ))}
                  </div>

                  {avgPing != null && <div className="text-[var(--proto-text-muted)]/60">avg latency {avgPing}ms</div>}
                </>
              )}

              {/* Hint */}
              {!expanded && <div className="text-[var(--proto-text-muted)]/40 text-[10px]">Hold Shift for details</div>}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
