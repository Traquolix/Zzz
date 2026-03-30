import { useState, useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { getFiberColor, getSpeedColor } from '../data'
import { useFiberData } from '../context/FiberContext'
import { COLORS } from '@/lib/theme'
import type { MapPageAction, Section, SelectedChannel } from '../types'
import { useRealtime } from '@/hooks/useRealtime'
import { parseDetections } from '@/lib/parseMessage'
import { DetailHeader } from './DetailHeader'
import { MetricCard } from './MetricCard'
import { ColorDot } from './ColorDot'

export function ChannelDetail({
  channel,
  sections,
  dispatch,
  fiberColors,
}: {
  channel: SelectedChannel
  sections: Section[]
  dispatch: React.Dispatch<MapPageAction>
  fiberColors: Record<string, string>
}) {
  const { t } = useTranslation()
  const { findFiber } = useFiberData()
  const fiber = findFiber(channel.fiberId, channel.direction)
  const fiberColor = fiber ? getFiberColor(fiber, fiberColors) : COLORS.chart.speed
  const directionLabel = fiber?.direction === 0 ? 'Dir A' : 'Dir B'

  // Find sections containing this channel
  const containingSections = sections.filter(
    s =>
      s.fiberId === channel.fiberId &&
      s.direction === channel.direction &&
      channel.channel >= s.startChannel &&
      channel.channel <= s.endChannel,
  )

  // Live speed data from WebSocket
  const { subscribe } = useRealtime()
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const dotsRef = useRef<{ time: number; speed: number }[]>([])
  const statsRef = useRef({ count: 0, speedSum: 0 })
  const [liveCount, setLiveCount] = useState(0)
  const [liveAvgSpeed, setLiveAvgSpeed] = useState<number | null>(null)

  // Reset on channel change
  useEffect(() => {
    dotsRef.current = []
    statsRef.current = { count: 0, speedSum: 0 }
    setLiveCount(0)
    setLiveAvgSpeed(null)
  }, [channel.fiberId, channel.channel])

  // Subscribe to detections and collect speed dots
  useEffect(() => {
    const NEIGHBOR_RANGE = 0

    const unsub = subscribe('detections', (data: unknown) => {
      const detections = parseDetections(data)

      for (const d of detections) {
        if (d.fiberId !== channel.fiberId || d.direction !== channel.direction) continue
        if (Math.abs(d.channel - channel.channel) > NEIGHBOR_RANGE) continue
        dotsRef.current.push({ time: Date.now(), speed: d.speed })
      }
    })
    return unsub
  }, [subscribe, channel.fiberId, channel.direction, channel.channel])

  // Canvas render loop + stats update
  useEffect(() => {
    let rafId: number
    const WINDOW_MS = 60_000 // 60s rolling window
    const STATS_WINDOW_MS = 60_000 // 60s for stats
    const FRAME_INTERVAL = 1000 / 30 // 30fps cap
    let lastFrameTime = 0

    function render(time: number) {
      // Throttle to 30fps
      if (time - lastFrameTime < FRAME_INTERVAL) {
        rafId = requestAnimationFrame(render)
        return
      }
      lastFrameTime = time

      const canvas = canvasRef.current
      if (!canvas) {
        rafId = requestAnimationFrame(render)
        return
      }
      const ctx = canvas.getContext('2d')
      if (!ctx) {
        rafId = requestAnimationFrame(render)
        return
      }

      const now = Date.now()
      const cutoff = now - WINDOW_MS
      const statsCutoff = now - STATS_WINDOW_MS

      // Prune old dots — find cutoff index and splice once (O(n) vs O(n²) shift loop)
      const dots = dotsRef.current
      let pruneIdx = 0
      while (pruneIdx < dots.length && dots[pruneIdx].time < cutoff) pruneIdx++
      if (pruneIdx > 0) dots.splice(0, pruneIdx)

      // Compute stats (last 60s)
      let count = 0
      let speedSum = 0
      for (const dot of dotsRef.current) {
        if (dot.time >= statsCutoff) {
          count++
          speedSum += dot.speed
        }
      }
      statsRef.current = { count, speedSum }

      const dpr = window.devicePixelRatio || 1
      const w = canvas.clientWidth
      const h = canvas.clientHeight
      canvas.width = w * dpr
      canvas.height = h * dpr
      ctx.scale(dpr, dpr)

      // Clear (transparent — panel background shows through)
      ctx.clearRect(0, 0, w, h)

      // Grid lines
      const maxSpeed = 140
      ctx.strokeStyle = COLORS.shmChart.canvasGrid
      ctx.lineWidth = 1
      for (const spd of [0, 30, 60, 90, 120]) {
        const y = h - (spd / maxSpeed) * h
        ctx.beginPath()
        ctx.moveTo(0, y)
        ctx.lineTo(w, y)
        ctx.stroke()
      }

      // Y-axis labels
      ctx.fillStyle = COLORS.shmChart.canvasLabel
      ctx.font = '9px monospace'
      ctx.textAlign = 'left'
      for (const spd of [30, 60, 90, 120]) {
        const y = h - (spd / maxSpeed) * h
        ctx.fillText(`${spd}`, 2, y - 2)
      }

      // Draw dots
      for (const dot of dotsRef.current) {
        const x = ((dot.time - cutoff) / WINDOW_MS) * w
        const y = h - (Math.min(dot.speed, maxSpeed) / maxSpeed) * h
        const age = (now - dot.time) / WINDOW_MS
        const alpha = 1 - age * 0.7

        ctx.globalAlpha = alpha
        ctx.beginPath()
        ctx.arc(x, y, 2.5, 0, Math.PI * 2)
        ctx.fillStyle = getSpeedColor(dot.speed)
        ctx.fill()
      }
      ctx.globalAlpha = 1

      rafId = requestAnimationFrame(render)
    }

    rafId = requestAnimationFrame(render)
    return () => cancelAnimationFrame(rafId)
  }, [channel.fiberId, channel.channel])

  // Stats update at 2Hz
  useEffect(() => {
    const timer = setInterval(() => {
      const { count, speedSum } = statsRef.current
      setLiveCount(count)
      setLiveAvgSpeed(count > 0 ? Math.round(speedSum / count) : null)
    }, 500)
    return () => clearInterval(timer)
  }, [])

  const speedColor = liveAvgSpeed != null ? getSpeedColor(liveAvgSpeed) : undefined

  return (
    <div className="dash-analysis-enter flex flex-col">
      <DetailHeader
        title={`Channel ${channel.channel}`}
        subtitle={
          <span className="text-cq-2xs text-[var(--dash-text-muted)] flex items-center gap-1.5">
            <ColorDot color={fiberColor} />
            {fiber?.name ?? channel.fiberId} · {directionLabel} · {channel.lat.toFixed(5)}N, {channel.lng.toFixed(5)}E
          </span>
        }
      />

      <div className="px-4 py-4 flex flex-col gap-3">
        {/* KPI cards — 2-column grid */}
        <div className="grid grid-cols-2 gap-3">
          <MetricCard label="Detections" value={liveCount} unit={t('channelDetail.detectionsWindow')} />
          <MetricCard
            label="Avg Speed"
            value={liveAvgSpeed != null ? liveAvgSpeed : '\u2014'}
            unit="km/h"
            valueColor={speedColor}
          />
        </div>

        {/* Live speed chart */}
        <div className="rounded-lg border border-[var(--dash-border)] overflow-hidden">
          <div className="px-3 py-2 flex items-center justify-between">
            <h3 className="text-cq-2xs font-medium text-[var(--dash-text-muted)] uppercase tracking-wider">
              Live Speed
            </h3>
            <span className="text-cq-2xs text-[var(--dash-text-muted)]">(60s)</span>
          </div>
          <canvas ref={canvasRef} className="w-full h-40 rounded-b-lg" />
        </div>

        {/* Containing sections */}
        <div>
          <h3 className="text-cq-2xs font-medium text-[var(--dash-text-muted)] uppercase tracking-wider mb-2">
            Sections
          </h3>
          {containingSections.length > 0 ? (
            <div className="flex flex-col gap-1.5">
              {containingSections.map(sec => {
                const secFiber = findFiber(sec.fiberId, sec.direction)
                const secColor = secFiber ? getFiberColor(secFiber, fiberColors) : COLORS.fiber.default
                return (
                  <button
                    key={sec.id}
                    onClick={() => dispatch({ type: 'SELECT_SECTION', id: sec.id })}
                    className="flex items-center gap-2.5 w-full text-left rounded-lg border border-[var(--dash-border)] px-3 py-2 hover:bg-[var(--dash-surface-raised)] transition-colors cursor-pointer"
                  >
                    <ColorDot color={secColor} />
                    <span className="text-cq-sm text-[var(--dash-text)] truncate flex-1">{sec.name}</span>
                    <span className="text-cq-2xs text-[var(--dash-text-muted)] flex-shrink-0 px-1.5 py-0.5 rounded bg-[var(--dash-base)]">
                      Ch {sec.startChannel}–{sec.endChannel}
                    </span>
                  </button>
                )
              })}
            </div>
          ) : (
            <p className="text-cq-xs text-[var(--dash-text-muted)] italic">No sections contain this channel</p>
          )}
        </div>
      </div>
    </div>
  )
}
