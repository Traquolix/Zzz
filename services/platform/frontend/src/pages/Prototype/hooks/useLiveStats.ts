import { useEffect, useState, useRef, useCallback } from 'react'
import { fetchSectionHistory, type SectionHistoryPoint } from '@/api/sections'
import { useRealtime } from '@/hooks/useRealtime'
import type { Section } from '../types'
import type { SectionDataPoint, LiveSectionStats } from '../types'

const POLL_INTERVAL = 2000 // 2 seconds
const HISTORY_MINUTES = 1 // minimal window — just enough for current stats + sparklines
const MAX_POINTS = 60 // 1 minute at 1s resolution

/**
 * Lightweight stats poller for all sections.
 *
 * Fetches the last minute of per-second data to derive current speed, flow,
 * occupancy, and short sparklines. Used by the map (section coloring) and
 * section list cards. The section detail view uses useSectionHistory instead
 * for time-range-aware chart data.
 */
export function useLiveStats(sections: Section[]) {
  const { flow } = useRealtime()
  const [stats, setStats] = useState<Map<string, LiveSectionStats>>(() => new Map())
  const [seriesData, setSeriesData] = useState<Map<string, SectionDataPoint[]>>(() => new Map())
  const sectionsRef = useRef(sections)
  sectionsRef.current = sections

  // Track the latest timestamp per section for incremental fetches
  const sinceRef = useRef<Map<string, number>>(new Map())
  // Store accumulated points per section
  const accumulatedRef = useRef<Map<string, SectionDataPoint[]>>(new Map())

  const fetchAll = useCallback(async () => {
    const secs = sectionsRef.current
    if (secs.length === 0) return

    const nextStats = new Map<string, LiveSectionStats>()
    const nextSeries = new Map<string, SectionDataPoint[]>()

    await Promise.all(
      secs.map(async sec => {
        try {
          const since = sinceRef.current.get(sec.id)
          const res = await fetchSectionHistory(sec.id, HISTORY_MINUTES, flow, since)
          const newPoints = mapPointsToSeries(res.points)

          // Merge with existing accumulated data
          let accumulated = accumulatedRef.current.get(sec.id) ?? []
          if (since == null) {
            accumulated = newPoints
          } else if (newPoints.length > 0) {
            accumulated.push(...newPoints)
          }

          // Trim to window
          const cutoff = Date.now() - HISTORY_MINUTES * 60 * 1000
          const firstValid = accumulated.findIndex(p => p.timestamp >= cutoff)
          if (firstValid > 0) accumulated.splice(0, firstValid)

          if (accumulated.length > MAX_POINTS) {
            accumulated.splice(0, accumulated.length - MAX_POINTS)
          }

          accumulatedRef.current.set(sec.id, accumulated)
          nextSeries.set(sec.id, accumulated)
          nextStats.set(sec.id, deriveStats(accumulated, sec))

          if (res.points.length > 0) {
            sinceRef.current.set(sec.id, res.points[res.points.length - 1].time)
          }
        } catch {
          // Keep previous data on error
        }

        // Preserve existing data if fetch failed
        if (!nextSeries.has(sec.id)) {
          const existing = accumulatedRef.current.get(sec.id)
          if (existing && existing.length > 0) {
            nextSeries.set(sec.id, existing)
            nextStats.set(sec.id, deriveStats(existing, sec))
          }
        }
      }),
    )

    if (nextSeries.size > 0) {
      setSeriesData(nextSeries)
      setStats(nextStats)
    }
  }, [flow])

  useEffect(() => {
    sinceRef.current.clear()
    accumulatedRef.current.clear()
    setStats(new Map())
    setSeriesData(new Map())
    fetchAll()
    const timer = setInterval(fetchAll, POLL_INTERVAL)
    return () => clearInterval(timer)
  }, [fetchAll])

  return { stats, seriesData }
}

/** Map API history points to frontend SectionDataPoint shape. */
function mapPointsToSeries(points: SectionHistoryPoint[]): SectionDataPoint[] {
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

/** Derive current stats from the most recent data points. */
export function deriveStats(series: SectionDataPoint[], section: Section): LiveSectionStats {
  if (series.length === 0) {
    return { avgSpeed: null, flow: null, travelTime: null, occupancy: null }
  }

  const recent = series.slice(-10)
  const avgSpeed = Math.round(recent.reduce((a, p) => a + p.speed, 0) / recent.length)
  const avgFlow = Math.round(recent.reduce((a, p) => a + p.flow, 0) / recent.length)
  const avgOccupancy = Math.round(recent.reduce((a, p) => a + p.occupancy, 0) / recent.length)

  const channelRange = section.endChannel - section.startChannel
  const travelTime = avgSpeed > 0 ? (channelRange * 5) / ((avgSpeed * 1000) / 3600) / 60 : null

  return {
    avgSpeed,
    flow: avgFlow,
    travelTime: travelTime ? Math.round(travelTime * 10) / 10 : null,
    occupancy: avgOccupancy,
  }
}
