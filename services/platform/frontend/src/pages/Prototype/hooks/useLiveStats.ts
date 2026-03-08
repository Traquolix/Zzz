import { useRef, useEffect, useState, useCallback } from 'react'
import { CircularBuffer } from '@/lib/CircularBuffer'
import { parseDetections } from '@/lib/parseMessage'
import { useRealtime } from '@/hooks/useRealtime'
import { useFlowReset } from '@/hooks/useFlowReset'
import { fiberLineId } from '../data'
import type { Detection } from '@/types/realtime'
import type { Section } from '../types'
import type { SectionDataPoint, LiveSectionStats } from '../types'

const FLUSH_INTERVAL = 500 // 2Hz
const MAX_PENDING = 5000
const HISTORY_SIZE = 7200 // 1 hour at 2Hz

interface SectionBuffer {
  buffer: CircularBuffer<SectionDataPoint>
  rawCounts: CircularBuffer<number>
}

export function useLiveStats(sections: Section[]) {
  const { subscribe } = useRealtime()
  const pendingRef = useRef<Detection[]>([])
  const sectionsRef = useRef(sections)
  sectionsRef.current = sections

  const buffersRef = useRef(new Map<string, SectionBuffer>())

  const [stats, setStats] = useState<Map<string, LiveSectionStats>>(() => new Map())
  const statsRef = useRef<Map<string, LiveSectionStats>>(new Map())
  const [seriesData, setSeriesData] = useState<Map<string, SectionDataPoint[]>>(() => new Map())

  // Clear accumulated state on flow switch
  useFlowReset(() => {
    pendingRef.current = []
    buffersRef.current.clear()
    statsRef.current = new Map()
    setStats(new Map())
    setSeriesData(new Map())
  })

  // Ensure buffers exist for all sections
  const ensureBuffers = useCallback((secs: Section[]) => {
    for (const sec of secs) {
      if (!buffersRef.current.has(sec.id)) {
        buffersRef.current.set(sec.id, {
          buffer: new CircularBuffer<SectionDataPoint>(HISTORY_SIZE),
          rawCounts: new CircularBuffer<number>(HISTORY_SIZE),
        })
      }
    }
  }, [])

  // Subscribe to detections
  useEffect(() => {
    const unsub = subscribe('detections', (data: unknown) => {
      const detections = parseDetections(data)
      if (detections.length === 0) return

      const pending = pendingRef.current
      if (pending.length < MAX_PENDING) {
        pending.push(...detections)
      } else {
        // Drop oldest to make room
        const overflow = pending.length + detections.length - MAX_PENDING
        if (overflow > 0) pending.splice(0, overflow)
        pending.push(...detections)
      }
    })
    return unsub
  }, [subscribe])

  // 2Hz flush
  useEffect(() => {
    const timer = setInterval(() => {
      const batch = pendingRef.current
      if (batch.length === 0) return
      pendingRef.current = []

      const secs = sectionsRef.current
      ensureBuffers(secs)

      const now = Date.now()
      const timeStr = new Date(now).toLocaleTimeString([], {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
      })

      const nextStats = new Map<string, LiveSectionStats>()
      const nextSeries = new Map<string, SectionDataPoint[]>()

      for (const sec of secs) {
        // Filter detections belonging to this section
        const matching = batch.filter(
          d =>
            fiberLineId(d.fiberId, d.direction) === sec.fiberId &&
            d.channel >= sec.startChannel &&
            d.channel <= sec.endChannel,
        )

        const sb = buffersRef.current.get(sec.id)
        if (!sb) continue

        if (matching.length > 0) {
          // Weighted avg speed: sum(speed * count) / sum(count)
          let speedSum = 0
          let countSum = 0
          for (const d of matching) {
            speedSum += d.speed * d.count
            countSum += d.count
          }
          const avgSpeed = countSum > 0 ? speedSum / countSum : 0

          // Travel time: (channelRange * 5m) / (avgSpeed km/h → m/s) / 60 → minutes
          const channelRange = sec.endChannel - sec.startChannel
          const travelTime = avgSpeed > 0 ? (channelRange * 5) / ((avgSpeed * 1000) / 3600) / 60 : null

          const AVG_VEHICLE_LENGTH = 6 // meters

          // Estimate cross-section flow: countSum spans many channels,
          // but we want the count at a single point. Divide by the
          // number of channels that actually reported to get the
          // average per-channel count (≈ cross-section vehicle count).
          const reportingChannels = new Set(matching.map(d => d.channel)).size
          sb.rawCounts.push(countSum / reportingChannels)

          // Compute rolling flow (last 20 entries = 10 seconds at 2Hz)
          const ROLLING_WINDOW = 20
          const recent = sb.rawCounts.lastN(ROLLING_WINDOW)
          const totalCount = recent.reduce((a, b) => a + b, 0)
          const windowSeconds = recent.length * (FLUSH_INTERVAL / 1000)
          const rollingFlowPerHour = Math.round((totalCount / windowSeconds) * 3600)
          const rollingFlowPerMin = Math.round(rollingFlowPerHour / 60)

          // Compute occupancy using veh/h internally: (flow_veh_h * vehicle_length_m) / (speed_m_s * 1000)
          const speedMs = avgSpeed * (1000 / 3600)
          const occupancy =
            speedMs > 0
              ? Math.min(100, Math.round((rollingFlowPerHour * AVG_VEHICLE_LENGTH) / (speedMs * 1000)))
              : countSum > 0
                ? 100
                : 0

          sb.buffer.push({
            time: timeStr,
            timestamp: now,
            speed: Math.round(avgSpeed),
            flow: rollingFlowPerMin,
            occupancy,
          })

          nextStats.set(sec.id, {
            avgSpeed: Math.round(avgSpeed),
            flow: rollingFlowPerMin,
            travelTime: travelTime ? Math.round(travelTime * 10) / 10 : null,
            occupancy,
          })
        } else {
          // Push zero so rolling window reflects no-traffic periods
          sb.rawCounts.push(0)
          // Keep previous stats if available
          const prev = statsRef.current.get(sec.id)
          if (prev) nextStats.set(sec.id, prev)
        }

        nextSeries.set(sec.id, sb.buffer.toArray())
      }

      statsRef.current = nextStats
      setStats(nextStats)
      setSeriesData(nextSeries)
    }, FLUSH_INTERVAL)

    return () => clearInterval(timer)
  }, [ensureBuffers])

  return { stats, seriesData }
}
