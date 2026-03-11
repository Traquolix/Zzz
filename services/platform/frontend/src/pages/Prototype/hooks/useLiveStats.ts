import { useRef, useMemo, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { fetchBatchSectionHistory } from '@/api/sections'
import { useRealtime } from '@/hooks/useRealtime'
import { logger } from '@/lib/logger'
import type { Section, SectionDataPoint, LiveSectionStats } from '../types'
import { mapHistoryPoints } from './mapHistoryPoints'

const POLL_INTERVAL = 2000 // 2 seconds
const HISTORY_MINUTES = 1 // minimal window — just enough for current stats + sparklines
const MAX_POINTS = 60 // 1 minute at 1s resolution

/**
 * Lightweight stats poller for all sections.
 *
 * Fetches the last minute of per-second data to derive current speed, flow,
 * occupancy, and short sparklines. Uses a single batch endpoint instead of
 * N parallel requests. The section detail view uses useSectionHistory for
 * time-range-aware chart data.
 *
 * React Query's refetchInterval auto-pauses when the tab is hidden.
 */
export function useLiveStats(sections: Section[]) {
  const { flow } = useRealtime()
  const sectionsRef = useRef(sections)
  sectionsRef.current = sections

  // Per-section since cursors sent to the backend so each section
  // only returns points after its own last-known timestamp.
  const sinceRef = useRef<Map<string, number>>(new Map())
  // Store accumulated points per section
  const accumulatedRef = useRef<Map<string, SectionDataPoint[]>>(new Map())

  // Last non-empty result — preserved when a poll cycle returns no new points
  const lastResultRef = useRef<{
    stats: Map<string, LiveSectionStats>
    seriesData: Map<string, SectionDataPoint[]>
  } | null>(null)

  // Generation counter: incremented on every key change. The queryFn captures
  // the current generation before awaiting; if it differs after the await,
  // the response is stale and ref writes are skipped.
  const generationRef = useRef(0)

  const sectionIds = useMemo(
    () =>
      sections
        .map(s => s.id)
        .sort()
        .join(','),
    [sections],
  )

  // Reset cursors outside queryFn so concurrent retries don't corrupt state.
  useEffect(() => {
    generationRef.current += 1
    sinceRef.current.clear()
    accumulatedRef.current.clear()
    lastResultRef.current = null
  }, [sectionIds, flow])

  const { data, error } = useQuery({
    queryKey: ['live-stats', sectionIds, flow],
    queryFn: async () => {
      const gen = generationRef.current
      const secs = sectionsRef.current

      if (secs.length === 0) {
        return { stats: new Map<string, LiveSectionStats>(), seriesData: new Map<string, SectionDataPoint[]>() }
      }

      // Build per-section since map — backend applies each cursor individually
      const sinceMap: Record<string, number> = {}
      for (const sec of secs) {
        const since = sinceRef.current.get(sec.id)
        if (since != null) sinceMap[sec.id] = since
      }

      const batchResult = await fetchBatchSectionHistory(
        secs.map(s => s.id),
        HISTORY_MINUTES,
        flow,
        Object.keys(sinceMap).length > 0 ? sinceMap : undefined,
      )

      // Stale response from a previous key — discard ref writes
      if (gen !== generationRef.current) {
        return (
          lastResultRef.current ?? {
            stats: new Map<string, LiveSectionStats>(),
            seriesData: new Map<string, SectionDataPoint[]>(),
          }
        )
      }

      const nextStats = new Map<string, LiveSectionStats>()
      const nextSeries = new Map<string, SectionDataPoint[]>()

      for (const sec of secs) {
        const rawPoints = batchResult[sec.id]
        if (!rawPoints) {
          // Section not in response (e.g. filtered out by org scoping) — keep existing
          const existing = accumulatedRef.current.get(sec.id)
          if (existing && existing.length > 0) {
            nextSeries.set(sec.id, existing)
            nextStats.set(sec.id, deriveStats(existing, sec))
          }
          continue
        }

        const newPoints = mapHistoryPoints(rawPoints)

        // Merge with existing accumulated data
        let accumulated = accumulatedRef.current.get(sec.id) ?? []
        if (!sinceRef.current.has(sec.id)) {
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

        if (rawPoints.length > 0) {
          sinceRef.current.set(sec.id, rawPoints[rawPoints.length - 1].time)
        }
      }

      const result = { stats: nextStats, seriesData: nextSeries }

      // Preserve previous data when all sections return empty (e.g. no new
      // points in this poll cycle) to avoid briefly clearing sparklines.
      if (nextSeries.size === 0 && secs.length > 0 && lastResultRef.current) {
        return lastResultRef.current
      }

      if (nextSeries.size > 0) {
        lastResultRef.current = result
      }

      return result
    },
    refetchInterval: POLL_INTERVAL,
    staleTime: 0,
  })

  useEffect(() => {
    if (error) logger.error('useLiveStats: batch fetch failed', error)
  }, [error])

  return {
    stats: data?.stats ?? new Map<string, LiveSectionStats>(),
    seriesData: data?.seriesData ?? new Map<string, SectionDataPoint[]>(),
  }
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
