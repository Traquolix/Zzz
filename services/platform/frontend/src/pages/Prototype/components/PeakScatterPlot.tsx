import { useState, useMemo, useCallback, useRef } from 'react'
import { useDebouncedResize } from '../hooks/useDebouncedResize'
import type { PeakFrequencyData } from '@/types/infrastructure'
import { computeHourTicks } from './ShmCharts'

type ScatterTooltip = { x: number; y: number; freq: number; power: number; timestamp: Date } | null
type ScatterBrush = { startX: number; currentX: number } | null
type ScatterZoom = { startMs: number; endMs: number } | null

export function PeakScatterPlot({ data }: { data: PeakFrequencyData }) {
  const containerRef = useRef<HTMLDivElement>(null)
  const svgRef = useRef<SVGSVGElement>(null)
  const { width, transitioning } = useDebouncedResize(containerRef)
  const [tooltip, setTooltip] = useState<ScatterTooltip>(null)
  const [brush, setBrush] = useState<ScatterBrush>(null)
  const [zoom, setZoom] = useState<ScatterZoom>(null)
  const rawId = useRef(Math.random().toString(36).slice(2)).current
  const clipId = `proto-scatter-${rawId}`

  const height = 170
  const padding = { top: 16, right: 12, bottom: 28, left: 48 }
  const plotW = width - padding.left - padding.right
  const plotH = height - padding.top - padding.bottom

  const t0 = useMemo(() => new Date(data.t0), [data.t0])

  const fullTimeRange = useMemo(() => {
    const min = t0.getTime()
    const max = min + (data.dt[data.dt.length - 1] || 0) * 1000
    return { min, max }
  }, [t0, data.dt])

  const timeRange = useMemo(() => {
    if (zoom) return { min: zoom.startMs, max: zoom.endMs }
    return fullTimeRange
  }, [zoom, fullTimeRange])

  const { points, xScale, yScale, freqMin, freqMax, inverseXScale } = useMemo(() => {
    const freqMin = 1.06
    const freqMax = 1.16

    let pMin = Infinity,
      pMax = -Infinity
    for (const p of data.peakPowers) {
      if (p < pMin) pMin = p
      if (p > pMax) pMax = p
    }
    const { min: timeMin, max: timeMax } = timeRange
    const xScale = (ms: number) => padding.left + ((ms - timeMin) / (timeMax - timeMin || 1)) * plotW
    const yScale = (f: number) => padding.top + ((freqMax - f) / (freqMax - freqMin || 1)) * plotH
    const inverseXScale = (px: number) => timeMin + ((px - padding.left) / plotW) * (timeMax - timeMin)

    const pts = data.dt.map((offsetSec, i) => {
      const ts = new Date(t0.getTime() + offsetSec * 1000)
      const ms = ts.getTime()
      const freq = data.peakFrequencies[i]
      return {
        x: xScale(ms),
        y: yScale(freq),
        freq,
        power: data.peakPowers[i],
        timestamp: ts,
        size: 2 + ((data.peakPowers[i] - pMin) / (pMax - pMin + 1e-10)) * 4,
        inRange: freq >= freqMin && freq <= freqMax,
        inTimeRange: ms >= timeMin && ms <= timeMax,
      }
    })
    return { points: pts, xScale, yScale, freqMin, freqMax, inverseXScale }
  }, [data, t0, plotW, plotH, padding.left, padding.top, timeRange])

  const yTicks = useMemo(() => {
    const count = 5
    const step = (freqMax - freqMin) / (count - 1)
    return Array.from({ length: count }, (_, i) => freqMin + i * step)
  }, [freqMin, freqMax])

  const xTicks = useMemo(() => {
    const { min: tMin, max: tMax } = timeRange
    return computeHourTicks(tMin, tMax).map(t => ({ x: xScale(tMin + t.frac * (tMax - tMin)), label: t.label }))
  }, [timeRange, xScale])

  // Brush handlers
  const getMouseX = useCallback((e: React.MouseEvent) => {
    if (!svgRef.current) return 0
    return e.clientX - svgRef.current.getBoundingClientRect().left
  }, [])

  const handleMouseDown = useCallback(
    (e: React.MouseEvent) => {
      const x = getMouseX(e)
      if (x >= padding.left && x <= width - padding.right) {
        setBrush({ startX: x, currentX: x })
        setTooltip(null)
      }
    },
    [getMouseX, padding.left, width, padding.right],
  )

  const handleMouseMove = useCallback(
    (e: React.MouseEvent) => {
      if (brush) {
        const x = Math.max(padding.left, Math.min(width - padding.right, getMouseX(e)))
        setBrush(prev => (prev ? { ...prev, currentX: x } : null))
      }
    },
    [brush, getMouseX, padding.left, width, padding.right],
  )

  const handleMouseUp = useCallback(() => {
    if (brush) {
      const minX = Math.min(brush.startX, brush.currentX)
      const maxX = Math.max(brush.startX, brush.currentX)
      if (maxX - minX > 10) setZoom({ startMs: inverseXScale(minX), endMs: inverseXScale(maxX) })
      setBrush(null)
    }
  }, [brush, inverseXScale])

  const brushRect = brush
    ? { x: Math.min(brush.startX, brush.currentX), width: Math.abs(brush.currentX - brush.startX) }
    : null

  if (!data.dt.length) return <div className="h-[170px]" ref={containerRef} />

  if (transitioning) {
    return (
      <div ref={containerRef} className="relative h-[170px]">
        <div className="w-full h-full rounded-lg bg-[var(--proto-surface-raised)] animate-pulse" />
      </div>
    )
  }

  return (
    <div ref={containerRef} className="w-full relative">
      {zoom && (
        <button
          onClick={() => setZoom(null)}
          className="absolute top-0 right-0 z-10 flex items-center gap-1 px-2 py-1 text-[length:var(--text-2xs)] text-[var(--proto-text-muted)] hover:text-[var(--proto-text)] rounded transition-colors cursor-pointer"
        >
          ↺ Reset
        </button>
      )}
      <div className="overflow-hidden">
        <svg
          ref={svgRef}
          width="100%"
          height={height}
          viewBox={`0 0 ${width} ${height}`}
          preserveAspectRatio="xMidYMid meet"
          className="select-none"
          onMouseDown={handleMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          onMouseLeave={() => {
            if (brush) setBrush(null)
          }}
          onDoubleClick={() => setZoom(null)}
        >
          <defs>
            <clipPath id={clipId}>
              <rect x={padding.left} y={padding.top} width={plotW} height={plotH} />
            </clipPath>
          </defs>

          {/* Y-axis */}
          <line
            x1={padding.left}
            y1={padding.top}
            x2={padding.left}
            y2={height - padding.bottom}
            stroke="rgba(255,255,255,0.08)"
            strokeWidth={1}
          />
          {yTicks.map(tick => (
            <g key={tick}>
              <line
                x1={padding.left - 3}
                y1={yScale(tick)}
                x2={padding.left}
                y2={yScale(tick)}
                stroke="#64748b"
                strokeWidth={1}
              />
              <text
                x={padding.left - 6}
                y={yScale(tick)}
                textAnchor="end"
                dominantBaseline="middle"
                fill="#64748b"
                fontSize="10"
              >
                {tick.toFixed(2)}
              </text>
            </g>
          ))}
          <text
            x={4}
            y={height / 2}
            textAnchor="middle"
            dominantBaseline="middle"
            transform={`rotate(-90, 4, ${height / 2})`}
            fill="#64748b"
            fontSize="9"
          >
            Peak Freq (Hz)
          </text>

          {/* X-axis */}
          <line
            x1={padding.left}
            y1={height - padding.bottom}
            x2={width - padding.right}
            y2={height - padding.bottom}
            stroke="rgba(255,255,255,0.08)"
            strokeWidth={1}
          />
          {xTicks.map((tick, i) => (
            <g key={i}>
              <line
                x1={tick.x}
                y1={height - padding.bottom}
                x2={tick.x}
                y2={height - padding.bottom + 3}
                stroke="#64748b"
                strokeWidth={1}
              />
              <text x={tick.x} y={height - padding.bottom + 14} textAnchor="middle" fill="#64748b" fontSize="10">
                {tick.label}
              </text>
            </g>
          ))}

          {/* Grid lines */}
          {yTicks.map(tick => (
            <line
              key={`g-${tick}`}
              x1={padding.left + 1}
              y1={yScale(tick)}
              x2={width - padding.right}
              y2={yScale(tick)}
              stroke="rgba(255,255,255,0.03)"
              strokeWidth={1}
            />
          ))}

          {/* Data points */}
          <g clipPath={`url(#${clipId})`}>
            {points
              .filter(pt => pt.inRange && pt.inTimeRange)
              .map((pt, i) => (
                <circle
                  key={i}
                  cx={pt.x}
                  cy={pt.y}
                  r={pt.size}
                  fill="#f59e0b"
                  fillOpacity={0.12}
                  stroke="none"
                  className="cursor-crosshair hover:!fill-opacity-60"
                  onMouseEnter={e => {
                    e.stopPropagation()
                    if (!brush)
                      setTooltip({ x: pt.x, y: pt.y, freq: pt.freq, power: pt.power, timestamp: pt.timestamp })
                  }}
                  onMouseLeave={() => setTooltip(null)}
                />
              ))}
          </g>

          {/* Brush */}
          {brushRect && (
            <rect
              x={brushRect.x}
              y={padding.top}
              width={brushRect.width}
              height={plotH}
              fill="var(--proto-accent)"
              fillOpacity={0.15}
              stroke="var(--proto-accent)"
              strokeWidth={1}
              pointerEvents="none"
            />
          )}
        </svg>
      </div>

      {/* Tooltip */}
      {tooltip && !brush && (
        <div
          className="absolute bg-[var(--proto-surface-raised)] text-[var(--proto-text)] text-[length:var(--text-2xs)] px-2 py-1.5 rounded shadow-lg pointer-events-none z-10 whitespace-nowrap border border-[var(--proto-border)]"
          style={{
            left: tooltip.x > width * 0.6 ? undefined : tooltip.x + 10,
            right: tooltip.x > width * 0.6 ? width - tooltip.x + 10 : undefined,
            top: tooltip.y - 10,
            transform: 'translateY(-100%)',
          }}
        >
          <div>Freq: {tooltip.freq.toFixed(3)} Hz</div>
          <div>Power: {tooltip.power.toFixed(2)}</div>
          <div className="text-[var(--proto-text-muted)]">
            {tooltip.timestamp.toLocaleString(undefined, {
              month: 'short',
              day: 'numeric',
              hour: '2-digit',
              minute: '2-digit',
            })}
          </div>
        </div>
      )}
    </div>
  )
}
