import { useRef, useEffect } from 'react'
import { useRealtime } from '@/hooks/useRealtime'
import { useFlowReset } from '@/hooks/useFlowReset'
import { parseDetections } from '@/lib/parseMessage'

export interface WaterfallDot {
  channel: number
  speed: number
  timestamp: number
  direction: 0 | 1
}

const DEFAULT_WINDOW_MS = 120_000

export function useWaterfallBuffer(fiberFilter: string, windowMs = DEFAULT_WINDOW_MS) {
  const { subscribe } = useRealtime()
  const dotsRef = useRef<WaterfallDot[]>([])
  const dirtyRef = useRef(false)
  const lastTsRef = useRef(0)

  // Clear buffer on flow switch
  useFlowReset(() => {
    dotsRef.current = []
    lastTsRef.current = 0
    dirtyRef.current = true
  })

  // Clear buffer when fiber changes
  useEffect(() => {
    dotsRef.current = []
    lastTsRef.current = 0
    dirtyRef.current = true
  }, [fiberFilter])

  useEffect(() => {
    const unsub = subscribe('detections', (data: unknown) => {
      const detections = parseDetections(data)
      if (detections.length === 0) return

      for (const d of detections) {
        if (d.fiberLine !== fiberFilter) continue
        dotsRef.current.push({
          channel: d.channel,
          speed: d.speed,
          timestamp: d.timestamp, // actual detection time from AI engine
          direction: d.direction,
        })
        if (d.timestamp > lastTsRef.current) {
          lastTsRef.current = d.timestamp
        }
      }

      dirtyRef.current = true
    })

    return unsub
  }, [subscribe, fiberFilter])

  /** Prune dots older than the visible window. Call during render. */
  function prune() {
    // Keep dots within windowMs of the latest detection
    const latest = lastTsRef.current || Date.now()
    const cutoff = latest - windowMs
    const dots = dotsRef.current
    const before = dots.length
    dotsRef.current = dots.filter(d => d.timestamp >= cutoff)
    if (dotsRef.current.length !== before) {
      dirtyRef.current = true
    }
  }

  return { dotsRef, dirtyRef, prune, lastTsRef }
}
