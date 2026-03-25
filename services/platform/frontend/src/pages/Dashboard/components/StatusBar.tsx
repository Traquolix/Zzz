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
  if (status === 'ok' || status === 'running') return 'var(--dash-green)'
  if (status === 'idle' || status === 'not_configured') return 'var(--dash-text-muted)'
  if (status === 'unknown') return 'var(--dash-amber)'
  return 'var(--dash-red)'
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

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => setShiftHeld(e.shiftKey)
    window.addEventListener('keydown', onKey)
    window.addEventListener('keyup', onKey)
    return () => {
      window.removeEventListener('keydown', onKey)
      window.removeEventListener('keyup', onKey)
    }
  }, [])

  const { data: backendVersion } = useQuery({
    queryKey: ['backend-version'],
    queryFn: async () => {
      const res = await fetch(`${API_URL}/api/health`, { cache: 'no-store' })
      if (!res.ok) return null
      const body = await res.json()
      return (body.version as string) ?? null
    },
    staleTime: Infinity,
    retry: false,
  })

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
      ? 'var(--dash-text-muted)'
      : lastPing < 0
        ? 'var(--dash-red)'
        : lastPing < 100
          ? 'var(--dash-green)'
          : lastPing < 300
            ? 'var(--dash-amber)'
            : 'var(--dash-red)'

  const infraReady = !readiness || readiness.status === 'ready'
  const overallColor = !connected ? 'var(--dash-red)' : infraReady ? 'var(--dash-green)' : 'var(--dash-amber)'
  const overallLabel = !connected ? 'Disconnected' : infraReady ? 'Operational' : 'Degraded'

  const detectionAge =
    lastDetectionTsRef?.current != null ? Math.round((Date.now() - lastDetectionTsRef.current) / 1000) : null

  const expanded = showTooltip && shiftHeld

  return (
    <div className="flex items-center gap-2.5">
      <span className="text-sm font-semibold text-[var(--dash-text)] tracking-tight">Sequoia Analytics</span>
      <div className="relative" onMouseEnter={() => setShowTooltip(true)} onMouseLeave={() => setShowTooltip(false)}>
        <span className="inline-flex items-center gap-1.5 text-[9px] font-medium px-1.5 py-0.5 rounded-full bg-[var(--dash-accent)]/20 text-[var(--dash-accent)] uppercase tracking-wider cursor-default relative -top-px">
          <span
            className={`w-1.5 h-1.5 rounded-full shrink-0 ${!connected ? 'animate-pulse' : ''}`}
            style={{ backgroundColor: overallColor }}
          />
          beta
        </span>
        {showTooltip && (
          <div
            className="absolute top-full mt-2 rounded-lg bg-[var(--dash-surface)] border border-[var(--dash-border)] shadow-xl z-50"
            style={{
              left: 0,
              width: expanded ? 280 : 264,
              backdropFilter: 'blur(12px)',
              background: 'linear-gradient(135deg, var(--dash-surface) 0%, rgba(43,45,49,0.95) 100%)',
            }}
          >
            {/* Header bar */}
            <div className="flex items-center justify-between px-3 py-2 border-b border-[var(--dash-border)]">
              <div className="flex items-center gap-2">
                <span
                  className="w-2 h-2 rounded-full shrink-0"
                  style={{
                    backgroundColor: overallColor,
                    boxShadow: `0 0 6px ${overallColor}`,
                  }}
                />
                <span className="text-[11px] font-semibold text-[var(--dash-text)] tracking-wide uppercase">
                  {overallLabel}
                </span>
              </div>
              {lastPing != null && lastPing > 0 && (
                <span className="text-[10px] text-[var(--dash-text-muted)] tabular-nums font-mono">{lastPing}ms</span>
              )}
            </div>

            <div className="px-3 py-2.5">
              {/* Latency sparkline */}
              {positivePings.length > 0 && (
                <div className="flex items-center gap-2.5 mb-2.5">
                  <div className="flex-1 overflow-hidden">
                    <Sparkline data={positivePings} color={pingColor} width={expanded ? 210 : 196} height={24} />
                  </div>
                  {avgPing != null && (
                    <span className="text-[10px] text-[var(--dash-text-muted)] tabular-nums font-mono shrink-0">
                      avg {avgPing}ms
                    </span>
                  )}
                </div>
              )}

              {/* Stats grid */}
              <div className="grid grid-cols-3 gap-px rounded overflow-hidden bg-[var(--dash-border)]">
                <div className="flex flex-col items-center py-1.5 px-1 bg-[var(--dash-surface)]">
                  <span className="text-[13px] font-semibold text-[var(--dash-text)] tabular-nums leading-none">
                    {sectionCount}
                  </span>
                  <span className="text-[9px] text-[var(--dash-text-muted)] uppercase tracking-wider mt-0.5">
                    Sections
                  </span>
                </div>
                <div className="flex flex-col items-center py-1.5 px-1 bg-[var(--dash-surface)]">
                  <span className="text-[13px] font-semibold text-[var(--dash-text)] tabular-nums leading-none">
                    {incidentCount}
                  </span>
                  <span className="text-[9px] text-[var(--dash-text-muted)] uppercase tracking-wider mt-0.5">
                    Incidents
                  </span>
                </div>
                <div className="flex flex-col items-center py-1.5 px-1 bg-[var(--dash-surface)]">
                  <span className="text-[13px] font-semibold text-[var(--dash-text)] tabular-nums leading-none">
                    {detectionAge != null ? `${detectionAge}s` : '—'}
                  </span>
                  <span className="text-[9px] text-[var(--dash-text-muted)] uppercase tracking-wider mt-0.5">
                    Data age
                  </span>
                </div>
              </div>

              {/* Expanded: service breakdown */}
              {expanded && (
                <div className="mt-2.5 pt-2.5 border-t border-[var(--dash-border)]">
                  <div className="text-[9px] text-[var(--dash-text-muted)] uppercase tracking-widest mb-1.5">
                    Services
                  </div>
                  <div className="flex flex-col gap-[3px]">
                    {/* Backend */}
                    <div className="flex items-center gap-2 py-[2px]">
                      <span
                        className="w-[5px] h-[5px] rounded-full shrink-0"
                        style={{ backgroundColor: connected ? 'var(--dash-green)' : 'var(--dash-red)' }}
                      />
                      <span className="text-[11px] text-[var(--dash-text-secondary)]">Backend</span>
                      <span className="text-[10px] text-[var(--dash-text-muted)] ml-auto font-mono">
                        {connected ? 'ok' : 'down'}
                      </span>
                    </div>

                    {readiness &&
                      Object.entries(readiness.checks).map(([key, status]) => (
                        <div key={key} className="flex items-center gap-2 py-[2px]">
                          <span
                            className="w-[5px] h-[5px] rounded-full shrink-0"
                            style={{ backgroundColor: statusColor(status) }}
                          />
                          <span className="text-[11px] text-[var(--dash-text-secondary)]">
                            {SERVICE_LABELS[key] ?? key}
                          </span>
                          <span className="text-[10px] text-[var(--dash-text-muted)] ml-auto font-mono">
                            {statusLabel(status)}
                          </span>
                        </div>
                      ))}
                  </div>
                </div>
              )}
            </div>

            {/* Footer — version + hint */}
            <div className="px-3 py-1.5 border-t border-[var(--dash-border)] flex items-center justify-between">
              <span className="text-[9px] text-[var(--dash-text-muted)]/40 font-mono tabular-nums">
                {__APP_VERSION__}
                {backendVersion && backendVersion !== 'dev' ? ` / ${backendVersion}` : ''}
              </span>
              {!expanded && (
                <span className="text-[9px] text-[var(--dash-text-muted)]/50 tracking-wide">
                  <kbd className="px-1 py-px rounded bg-[var(--dash-base)] text-[var(--dash-text-muted)] text-[8px] font-mono">
                    Shift
                  </kbd>
                </span>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
