import { useRef } from 'react'
import { useTranslation } from 'react-i18next'
import type { PeakFrequencyData } from '@/types/infrastructure'
import { COLORS } from '@/lib/theme'

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
  const { t } = useTranslation()
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

  const pointsA = processData(dataA, COLORS.shmChart.comparisonA)
  const pointsB = processData(dataB, COLORS.shmChart.comparisonB)
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
            stroke={COLORS.shmChart.axis}
            strokeWidth={1}
          />
          <text
            x={padding.left - 6}
            y={yScale(tick)}
            textAnchor="end"
            dominantBaseline="middle"
            fill={COLORS.shmChart.axis}
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
        fill={COLORS.shmChart.axis}
        fontSize="9"
      >
        {t('shm.frequencyHz')}
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
      <text x={padding.left} y={height - 4} textAnchor="start" fill={COLORS.shmChart.axisSecondary} fontSize="9">
        {t('shm.comparison.start')}
      </text>
      <text x={width - padding.right} y={height - 4} textAnchor="end" fill={COLORS.shmChart.axisSecondary} fontSize="9">
        {t('shm.comparison.end')}
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
