import { useEffect, useCallback, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { useDebouncedResize } from '../hooks/useDebouncedResize'
import type { SpectralTimeSeries } from '@/types/infrastructure'
import { computeHourTicks, VIRIDIS } from './shmUtils'

export function SpectralHeatmapCanvas({ data }: { data: SpectralTimeSeries }) {
  const { t } = useTranslation()
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
      ctx.fillText(t('shm.frequencyHz'), 0, 0)
      ctx.restore()
    },
    [data, t],
  )

  useEffect(() => {
    draw(debouncedWidth)
  }, [draw, debouncedWidth])

  return (
    <div ref={containerRef} className="w-full h-[200px]">
      {transitioning ? (
        <div className="w-full h-full rounded-lg bg-[var(--proto-surface-raised)] animate-pulse" />
      ) : (
        <canvas ref={canvasRef} className="rounded" />
      )}
    </div>
  )
}
