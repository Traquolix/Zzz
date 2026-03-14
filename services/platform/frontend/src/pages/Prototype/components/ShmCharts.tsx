import { useState, useMemo, useEffect, useCallback, useRef } from 'react'
import { useDebouncedResize } from '../hooks/useDebouncedResize'
import type { SpectralTimeSeries, PeakFrequencyData } from '@/types/infrastructure'

// ── Shared SHM helpers ───────────────────────────────────────────────

/** Compute hour-aligned tick positions for a time range. Returns {frac, label} tuples. */
export function computeHourTicks(tMin: number, tMax: number): { frac: number; label: string }[] {
  const ticks: { frac: number; label: string }[] = []
  const durH = (tMax - tMin) / (1000 * 3600)
  let interval = 1
  if (durH > 72) interval = 12
  else if (durH > 24) interval = 6
  else if (durH > 12) interval = 3
  else if (durH > 6) interval = 2
  // Align to the first interval-boundary hour at or after tMin.
  // Use local time only for alignment, then advance by fixed ms to avoid DST skips.
  const d = new Date(tMin)
  d.setMinutes(0, 0, 0)
  if (d.getTime() < tMin) d.setHours(d.getHours() + 1)
  const aligned = Math.ceil(d.getHours() / interval) * interval
  d.setHours(aligned)
  const intervalMs = interval * 3600_000
  let ts = d.getTime()
  while (ts <= tMax) {
    if (ts >= tMin) {
      ticks.push({
        frac: (ts - tMin) / (tMax - tMin || 1),
        label: `${new Date(ts).getHours().toString().padStart(2, '0')}:00`,
      })
    }
    ts += intervalMs
  }
  return ticks
}

// ── Spectral heatmap (canvas) ────────────────────────────────────────

// Viridis colormap (256 colors, RGB)
export const VIRIDIS: [number, number, number][] = [
  [68, 1, 84],
  [68, 2, 86],
  [69, 4, 87],
  [69, 5, 89],
  [70, 7, 90],
  [70, 8, 92],
  [70, 10, 93],
  [70, 11, 94],
  [71, 13, 96],
  [71, 14, 97],
  [71, 16, 99],
  [71, 17, 100],
  [71, 19, 101],
  [72, 20, 103],
  [72, 22, 104],
  [72, 23, 105],
  [72, 24, 106],
  [72, 26, 108],
  [72, 27, 109],
  [72, 28, 110],
  [72, 29, 111],
  [72, 31, 112],
  [72, 32, 113],
  [72, 33, 115],
  [72, 35, 116],
  [72, 36, 117],
  [72, 37, 118],
  [72, 38, 119],
  [72, 40, 120],
  [72, 41, 121],
  [71, 42, 122],
  [71, 44, 122],
  [71, 45, 123],
  [71, 46, 124],
  [71, 47, 125],
  [70, 48, 126],
  [70, 50, 126],
  [70, 51, 127],
  [69, 52, 128],
  [69, 53, 129],
  [69, 55, 129],
  [68, 56, 130],
  [68, 57, 131],
  [68, 58, 131],
  [67, 60, 132],
  [67, 61, 132],
  [66, 62, 133],
  [66, 63, 133],
  [66, 64, 134],
  [65, 66, 134],
  [65, 67, 135],
  [64, 68, 135],
  [64, 69, 136],
  [63, 71, 136],
  [63, 72, 137],
  [62, 73, 137],
  [62, 74, 137],
  [62, 76, 138],
  [61, 77, 138],
  [61, 78, 138],
  [60, 79, 139],
  [60, 80, 139],
  [59, 82, 139],
  [59, 83, 140],
  [58, 84, 140],
  [58, 85, 140],
  [57, 86, 141],
  [57, 88, 141],
  [56, 89, 141],
  [56, 90, 141],
  [55, 91, 142],
  [55, 92, 142],
  [54, 94, 142],
  [54, 95, 142],
  [53, 96, 142],
  [53, 97, 142],
  [52, 98, 143],
  [52, 100, 143],
  [51, 101, 143],
  [51, 102, 143],
  [50, 103, 143],
  [50, 105, 143],
  [49, 106, 143],
  [49, 107, 143],
  [49, 108, 143],
  [48, 109, 143],
  [48, 111, 143],
  [47, 112, 143],
  [47, 113, 143],
  [46, 114, 143],
  [46, 116, 143],
  [46, 117, 143],
  [45, 118, 143],
  [45, 119, 143],
  [44, 121, 142],
  [44, 122, 142],
  [44, 123, 142],
  [43, 124, 142],
  [43, 126, 142],
  [43, 127, 141],
  [42, 128, 141],
  [42, 129, 141],
  [42, 131, 140],
  [41, 132, 140],
  [41, 133, 140],
  [41, 135, 139],
  [40, 136, 139],
  [40, 137, 138],
  [40, 138, 138],
  [40, 140, 137],
  [39, 141, 137],
  [39, 142, 136],
  [39, 144, 136],
  [39, 145, 135],
  [39, 146, 134],
  [38, 148, 134],
  [38, 149, 133],
  [38, 150, 132],
  [38, 152, 131],
  [38, 153, 131],
  [38, 154, 130],
  [38, 156, 129],
  [38, 157, 128],
  [39, 158, 127],
  [39, 160, 126],
  [39, 161, 125],
  [39, 163, 124],
  [39, 164, 123],
  [40, 165, 122],
  [40, 167, 121],
  [40, 168, 120],
  [41, 169, 119],
  [41, 171, 118],
  [42, 172, 117],
  [42, 174, 116],
  [43, 175, 115],
  [43, 176, 113],
  [44, 178, 112],
  [45, 179, 111],
  [45, 181, 110],
  [46, 182, 108],
  [47, 183, 107],
  [48, 185, 106],
  [48, 186, 104],
  [49, 188, 103],
  [50, 189, 102],
  [51, 190, 100],
  [52, 192, 99],
  [53, 193, 97],
  [54, 195, 96],
  [55, 196, 94],
  [56, 197, 93],
  [58, 199, 91],
  [59, 200, 90],
  [60, 201, 88],
  [62, 203, 86],
  [63, 204, 85],
  [64, 206, 83],
  [66, 207, 81],
  [67, 208, 80],
  [69, 210, 78],
  [71, 211, 76],
  [72, 212, 74],
  [74, 214, 72],
  [76, 215, 71],
  [78, 216, 69],
  [79, 218, 67],
  [81, 219, 65],
  [83, 220, 63],
  [85, 221, 61],
  [87, 223, 59],
  [89, 224, 57],
  [91, 225, 55],
  [94, 226, 53],
  [96, 227, 51],
  [98, 229, 49],
  [100, 230, 47],
  [103, 231, 45],
  [105, 232, 43],
  [107, 233, 41],
  [110, 234, 39],
  [112, 235, 37],
  [115, 236, 35],
  [117, 237, 33],
  [120, 238, 31],
  [122, 239, 29],
  [125, 240, 27],
  [127, 241, 25],
  [130, 242, 24],
  [133, 243, 22],
  [135, 244, 21],
  [138, 245, 19],
  [141, 245, 18],
  [143, 246, 17],
  [146, 247, 16],
  [149, 248, 15],
  [151, 249, 14],
  [154, 249, 14],
  [157, 250, 14],
  [160, 251, 13],
  [162, 251, 13],
  [165, 252, 13],
  [168, 253, 14],
  [171, 253, 14],
  [173, 254, 15],
  [176, 254, 16],
  [179, 255, 17],
  [182, 255, 18],
  [185, 255, 19],
  [187, 255, 21],
  [190, 255, 22],
  [193, 255, 24],
  [196, 255, 25],
  [199, 255, 27],
  [201, 255, 29],
  [204, 255, 31],
  [207, 255, 33],
  [210, 255, 35],
  [212, 255, 38],
  [215, 255, 40],
  [218, 255, 42],
  [220, 255, 45],
  [223, 255, 47],
  [226, 255, 50],
  [228, 255, 53],
  [231, 255, 55],
  [233, 255, 58],
  [236, 255, 61],
  [238, 255, 64],
  [241, 255, 67],
  [243, 255, 70],
  [246, 255, 73],
  [248, 255, 76],
  [250, 255, 79],
  [253, 255, 82],
]

export function SpectralHeatmapCanvas({ data }: { data: SpectralTimeSeries }) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const { width: debouncedWidth, transitioning } = useDebouncedResize(containerRef)

  const draw = useCallback(
    (width: number) => {
      const canvas = canvasRef.current
      if (!canvas || width <= 0) return

      const height = 200
      const dpr = window.devicePixelRatio || 1
      canvas.width = width * dpr
      canvas.height = height * dpr
      canvas.style.width = `${width}px`
      canvas.style.height = `${height}px`

      const ctx = canvas.getContext('2d')
      if (!ctx) return
      ctx.scale(dpr, dpr)

      const { spectra, freqs } = data
      if (!spectra.length || !freqs.length) return

      const margin = { top: 4, right: 8, bottom: 24, left: 36 }
      const plotW = width - margin.left - margin.right
      const plotH = height - margin.top - margin.bottom
      if (plotW <= 0 || plotH <= 0) return

      const numTime = spectra.length
      const numFreq = freqs.length

      // Find min/max power for color scaling
      let minP = Infinity,
        maxP = -Infinity
      for (const row of spectra) {
        for (const v of row) {
          if (v < minP) minP = v
          if (v > maxP) maxP = v
        }
      }
      const range = maxP - minP || 1

      // Draw heatmap
      const cellW = plotW / numTime
      const cellH = plotH / numFreq

      for (let ti = 0; ti < numTime; ti++) {
        for (let fi = 0; fi < numFreq; fi++) {
          const norm = (spectra[ti][fi] - minP) / range
          const idx = Math.floor(norm * (VIRIDIS.length - 1))
          const [r, g, b] = VIRIDIS[Math.max(0, Math.min(idx, VIRIDIS.length - 1))]
          ctx.fillStyle = `rgb(${r},${g},${b})`
          ctx.fillRect(
            margin.left + ti * cellW,
            margin.top + (numFreq - 1 - fi) * cellH,
            Math.ceil(cellW) + 1,
            Math.ceil(cellH) + 1,
          )
        }
      }

      // Axes
      ctx.fillStyle = '#64748b'
      ctx.font = '10px sans-serif'

      // X axis (time) — hour-aligned ticks
      ctx.textAlign = 'center'
      const t0 = new Date(data.t0)
      const tMin = t0.getTime()
      const tMax = tMin + (data.dt[data.dt.length - 1] || 0) * 1000
      for (const tick of computeHourTicks(tMin, tMax)) {
        const x = margin.left + tick.frac * plotW
        ctx.fillText(tick.label, x, height - 4)
      }

      // Y axis (frequency) — integer Hz ticks
      ctx.textAlign = 'right'
      const freqLo = Math.ceil(freqs[0])
      const freqHi = Math.floor(freqs[freqs.length - 1])
      for (let hz = freqLo; hz <= freqHi; hz++) {
        const frac = (hz - freqs[0]) / (freqs[freqs.length - 1] - freqs[0])
        const y = margin.top + (1 - frac) * plotH + 3
        ctx.fillText(`${hz}`, margin.left - 4, y)
      }

      // Rotated vertical label: "Freq (Hz)"
      ctx.save()
      ctx.font = '9px sans-serif'
      ctx.textAlign = 'center'
      const labelX = 12
      const labelY = margin.top + plotH / 2
      ctx.translate(labelX, labelY)
      ctx.rotate(-Math.PI / 2)
      ctx.fillText('Freq (Hz)', 0, 0)
      ctx.restore()
    },
    [data],
  )

  useEffect(() => {
    draw(debouncedWidth)
  }, [draw, debouncedWidth])

  return (
    <div ref={containerRef} className="w-full" style={{ height: 200 }}>
      {transitioning ? (
        <div className="w-full h-full rounded-lg bg-[var(--proto-surface-raised)] animate-pulse" />
      ) : (
        <canvas ref={canvasRef} className="rounded" />
      )}
    </div>
  )
}

// ── Peak scatter plot (SHM-style dot cloud) ─────────────────────────

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

// ── Comparison overlay scatter ───────────────────────────────────────

export type ComparisonMode = 'day' | 'week'
export type FocusMode = 'A' | 'equal' | 'B'

export function ComparisonOverlay({
  dataA,
  dataB,
  focus,
  width,
}: {
  dataA: PeakFrequencyData | null
  dataB: PeakFrequencyData | null
  focus: FocusMode
  width: number
}) {
  const rawId = useRef(Math.random().toString(36).slice(2)).current
  const clipId = `proto-overlay-${rawId}`
  const height = 140
  const padding = { top: 12, right: 12, bottom: 22, left: 48 }
  const plotW = Math.max(80, width - padding.left - padding.right)
  const plotH = height - padding.top - padding.bottom

  const freqMin = 1.06,
    freqMax = 1.16
  const yScale = (f: number) => padding.top + ((freqMax - f) / (freqMax - freqMin)) * plotH

  const processData = (data: PeakFrequencyData | null, color: string) => {
    if (!data || !data.dt.length) return []
    const duration = (data.dt[data.dt.length - 1] || 1) * 1000
    return data.dt.map((off, i) => {
      const nx = (off * 1000) / duration
      const freq = data.peakFrequencies[i]
      return { x: padding.left + nx * plotW, y: yScale(freq), freq, inRange: freq >= freqMin && freq <= freqMax, color }
    })
  }

  const pointsA = processData(dataA, '#3b82f6')
  const pointsB = processData(dataB, '#f59e0b')
  const opacityA = focus === 'A' ? 0.7 : focus === 'equal' ? 0.3 : 0.04
  const opacityB = focus === 'B' ? 0.7 : focus === 'equal' ? 0.3 : 0.04
  const yTicks = [1.06, 1.09, 1.12, 1.16]

  return (
    <svg
      width="100%"
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className="overflow-visible"
      preserveAspectRatio="xMidYMid meet"
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
          <line
            x1={padding.left + 1}
            y1={yScale(tick)}
            x2={width - padding.right}
            y2={yScale(tick)}
            stroke="rgba(255,255,255,0.03)"
            strokeWidth={1}
          />
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
        Freq (Hz)
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
      <text x={padding.left} y={height - 4} textAnchor="start" fill="#4a5568" fontSize="9">
        start
      </text>
      <text x={width - padding.right} y={height - 4} textAnchor="end" fill="#4a5568" fontSize="9">
        end
      </text>

      {/* Dots: render unfocused behind, focused in front */}
      <g clipPath={`url(#${clipId})`}>
        {focus !== 'A' &&
          pointsB
            .filter(p => p.inRange)
            .map((pt, i) => (
              <circle key={`b-${i}`} cx={pt.x} cy={pt.y} r={2.5} fill={pt.color} fillOpacity={opacityB} />
            ))}
        {pointsA
          .filter(p => p.inRange)
          .map((pt, i) => (
            <circle key={`a-${i}`} cx={pt.x} cy={pt.y} r={2.5} fill={pt.color} fillOpacity={opacityA} />
          ))}
        {focus === 'A' &&
          pointsB
            .filter(p => p.inRange)
            .map((pt, i) => (
              <circle key={`b2-${i}`} cx={pt.x} cy={pt.y} r={2.5} fill={pt.color} fillOpacity={opacityB} />
            ))}
      </g>
    </svg>
  )
}
