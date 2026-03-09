import { useEffect, useState, useRef, useCallback } from 'react'
import { fetchSectionHistory, type SectionHistoryPoint } from '@/api/sections'
import { useRealtime } from '@/hooks/useRealtime'
import type { SectionDataPoint } from '../types'

const POLL_INTERVAL = 2000

/** Map time range labels to API minutes parameter. */
const TIME_RANGE_MINUTES: Record<string, number> = {
  '1m': 1,
  '5m': 5,
  '15m': 15,
  '1h': 60,
}

/**
 * Polls section history for a single section with the correct time range.
 *
 * - 1m/5m → backend serves per-second buffer (1s resolution)
 * - 15m/1h → backend serves per-minute buffer (1min resolution)
 *
 * Resets and re-fetches when time range or flow changes.
 */
export function useSectionHistory(sectionId: string, timeRange: string) {
  const { flow } = useRealtime()
  const [series, setSeries] = useState<SectionDataPoint[]>([])
  const sinceRef = useRef<number | undefined>(undefined)
  const accumulatedRef = useRef<SectionDataPoint[]>([])

  const minutes = TIME_RANGE_MINUTES[timeRange] ?? 5

  const abortRef = useRef<AbortController | null>(null)

  const fetchData = useCallback(async () => {
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller

    try {
      const since = sinceRef.current
      const res = await fetchSectionHistory(sectionId, minutes, flow, since)
      if (controller.signal.aborted) return

      const newPoints = mapPoints(res.points)

      let accumulated = accumulatedRef.current
      if (since == null) {
        accumulated = newPoints
      } else if (newPoints.length > 0) {
        accumulated.push(...newPoints)
      }

      // Trim to window
      const cutoff = Date.now() - minutes * 60 * 1000
      const firstValid = accumulated.findIndex(p => p.timestamp >= cutoff)
      if (firstValid > 0) accumulated.splice(0, firstValid)

      accumulatedRef.current = accumulated
      setSeries([...accumulated])

      if (res.points.length > 0) {
        sinceRef.current = res.points[res.points.length - 1].time
      }
    } catch {
      // Keep previous data on error (includes aborted requests)
    }
  }, [sectionId, minutes, flow])

  // Reset on time range or flow change
  useEffect(() => {
    sinceRef.current = undefined
    accumulatedRef.current = []
    setSeries([])
    fetchData()
    const timer = setInterval(fetchData, POLL_INTERVAL)
    return () => {
      clearInterval(timer)
      abortRef.current?.abort()
    }
  }, [fetchData])

  return series
}

function mapPoints(points: SectionHistoryPoint[]): SectionDataPoint[] {
  return points.map(p => ({
    time: new Date(p.time).toLocaleTimeString([], {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    }),
    timestamp: p.time,
    speed: Math.round(p.speed),
    flow: p.flow,
    occupancy: p.occupancy,
  }))
}
