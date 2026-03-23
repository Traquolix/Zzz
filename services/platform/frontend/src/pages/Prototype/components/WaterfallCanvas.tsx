import { useRef, useEffect, useCallback } from 'react'
import { COLORS } from '@/lib/theme'
import { getSpeedColor } from '../data'
import type { WaterfallDot } from '../hooks/useWaterfallBuffer'

interface WaterfallCanvasProps {
  dotsRef: React.RefObject<WaterfallDot[]>
  dirtyRef: React.MutableRefObject<boolean>
  lastTsRef: React.RefObject<number>
  prune: () => void
  windowMs: number
  minChannel: number
  maxChannel: number
}

const BG = COLORS.waterfall.background
const GRID_COLOR = COLORS.waterfall.grid
const LABEL_COLOR = COLORS.waterfall.label
const DOT_SIZE = 3
const TARGET_FPS = 30
const FRAME_INTERVAL = 1000 / TARGET_FPS
const HEADROOM_MS = 0

export function WaterfallCanvas({
  dotsRef,
  dirtyRef,
  lastTsRef,
  prune,
  windowMs,
  minChannel,
  maxChannel,
}: WaterfallCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const rafRef = useRef(0)
  const lastFrameRef = useRef(0)

  const draw = useCallback(() => {
    const canvas = canvasRef.current
    const container = containerRef.current
    if (!canvas || !container) return

    const width = container.clientWidth
    const height = container.clientHeight
    if (width === 0 || height === 0) return

    const dpr = window.devicePixelRatio || 1
    canvas.width = width * dpr
    canvas.height = height * dpr
    canvas.style.width = `${width}px`
    canvas.style.height = `${height}px`

    const ctx = canvas.getContext('2d')
    if (!ctx) return
    ctx.scale(dpr, dpr)

    // Prune old dots
    prune()

    const margin = { top: 28, right: 12, bottom: 8, left: 56 }
    const plotW = width - margin.left - margin.right
    const plotH = height - margin.top - margin.bottom

    // Background
    ctx.fillStyle = BG
    ctx.fillRect(0, 0, width, height)

    // Top of waterfall = latest detection timestamp + small headroom
    // Falls back to wall clock - 90s if no detections yet
    const latestTs = lastTsRef.current || Date.now() - 90_000
    const tMax = latestTs + HEADROOM_MS
    const tMin = tMax - windowMs
    const chRange = maxChannel - minChannel || 1

    // Grid lines
    ctx.strokeStyle = GRID_COLOR
    ctx.lineWidth = 1

    // Vertical grid (channels on X-axis)
    const chStep = Math.max(1, Math.ceil(chRange / 8))
    for (let ch = Math.ceil(minChannel / chStep) * chStep; ch <= maxChannel; ch += chStep) {
      const x = margin.left + ((ch - minChannel) / chRange) * plotW
      ctx.beginPath()
      ctx.moveTo(x, margin.top)
      ctx.lineTo(x, margin.top + plotH)
      ctx.stroke()
    }

    // Horizontal grid (time on Y-axis) — fixed positions relative to "now"
    const timeStep = windowMs <= 60_000 ? 10_000 : 30_000
    for (let ago = 0; ago <= windowMs; ago += timeStep) {
      const y = margin.top + (ago / windowMs) * plotH
      ctx.beginPath()
      ctx.moveTo(margin.left, y)
      ctx.lineTo(margin.left + plotW, y)
      ctx.stroke()
    }

    // Plot border
    ctx.strokeStyle = GRID_COLOR
    ctx.strokeRect(margin.left, margin.top, plotW, plotH)

    // Draw dots
    const dots = dotsRef.current
    for (let i = 0; i < dots.length; i++) {
      const dot = dots[i]
      if (dot.timestamp < tMin || dot.timestamp > tMax) continue
      if (dot.channel < minChannel || dot.channel > maxChannel) continue

      const x = margin.left + ((dot.channel - minChannel) / chRange) * plotW
      // now at top, past at bottom
      const y = margin.top + ((tMax - dot.timestamp) / (tMax - tMin)) * plotH

      ctx.fillStyle = getSpeedColor(dot.speed)
      ctx.fillRect(x - DOT_SIZE / 2, y - DOT_SIZE / 2, DOT_SIZE, DOT_SIZE)
    }

    // Axis labels
    ctx.fillStyle = LABEL_COLOR
    ctx.font = '10px sans-serif'

    // X-axis (top): channel numbers
    ctx.textAlign = 'center'
    ctx.textBaseline = 'bottom'
    for (let ch = Math.ceil(minChannel / chStep) * chStep; ch <= maxChannel; ch += chStep) {
      const x = margin.left + ((ch - minChannel) / chRange) * plotW
      ctx.fillText(String(ch), x, margin.top - 4)
    }

    // Y-axis (left): wall-clock labels — fixed positions, most recent at top
    ctx.textAlign = 'right'
    ctx.textBaseline = 'middle'
    const topTime = new Date(tMax)
    for (let ago = 0; ago <= windowMs; ago += timeStep) {
      const y = margin.top + (ago / windowMs) * plotH
      const t = new Date(topTime.getTime() - ago)
      const label = `${String(t.getHours()).padStart(2, '0')}:${String(t.getMinutes()).padStart(2, '0')}:${String(t.getSeconds()).padStart(2, '0')}`
      ctx.fillText(label, margin.left - 4, y)
    }

    dirtyRef.current = false
  }, [dotsRef, dirtyRef, lastTsRef, prune, windowMs, minChannel, maxChannel])

  useEffect(() => {
    let running = true

    function loop(time: number) {
      if (!running) return
      if (time - lastFrameRef.current >= FRAME_INTERVAL) {
        lastFrameRef.current = time
        draw()
      }
      rafRef.current = requestAnimationFrame(loop)
    }

    rafRef.current = requestAnimationFrame(loop)

    const observer = new ResizeObserver(() => draw())
    if (containerRef.current) observer.observe(containerRef.current)

    return () => {
      running = false
      cancelAnimationFrame(rafRef.current)
      observer.disconnect()
    }
  }, [draw])

  return (
    <div ref={containerRef} className="w-full h-full min-h-[250px]">
      <canvas ref={canvasRef} className="rounded" />
    </div>
  )
}
