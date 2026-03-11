import { useRef, useState, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { fetchSectionHistory } from '@/api/sections'
import { useRealtime } from '@/hooks/useRealtime'
import { logger } from '@/lib/logger'
import type { SectionDataPoint } from '../types'
import { mapHistoryPoints } from './mapHistoryPoints'

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
 * React Query's refetchInterval auto-pauses when the tab is hidden.
 * Returns `stale: true` while awaiting the first fetch after a range/flow change,
 * NOT during regular 2s background polls.
 */
export function useSectionHistory(sectionId: string, timeRange: string) {
  const { flow } = useRealtime()
  const minutes = TIME_RANGE_MINUTES[timeRange] ?? 5

  const sinceRef = useRef<number | undefined>(undefined)
  const accumulatedRef = useRef<SectionDataPoint[]>([])

  // Generation counter: incremented on every key change. The queryFn captures
  // the current generation before awaiting; if it differs after the await,
  // the response is stale and ref writes are skipped.
  const generationRef = useRef(0)

  // Stale flag: true only during key transitions (range/flow/section change),
  // NOT during regular background polls (which would cause 2s flicker).
  // Uses useState (not useRef) so changes trigger a re-render — a ref mutation
  // after the useEffect would be invisible until the next unrelated render.
  const [keyChanged, setKeyChanged] = useState(true)

  // Reset cursors outside queryFn so concurrent retries don't double-append.
  useEffect(() => {
    generationRef.current += 1
    sinceRef.current = undefined
    accumulatedRef.current = []
    setKeyChanged(true)
  }, [sectionId, minutes, flow])

  const { data, isFetching, error } = useQuery({
    queryKey: ['section-history', sectionId, minutes, flow],
    queryFn: async () => {
      const gen = generationRef.current
      const since = sinceRef.current
      const res = await fetchSectionHistory(sectionId, minutes, flow, since)

      // Stale response from a previous key — discard ref writes.
      // The return value goes to the old key's cache entry (not the current UI),
      // so an empty array is safe here.
      if (gen !== generationRef.current) return []

      const newPoints = mapHistoryPoints(res.points)

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

      if (res.points.length > 0) {
        sinceRef.current = res.points[res.points.length - 1].time
      }

      // Clear the key-changed flag after first successful fetch for new key
      setKeyChanged(false)

      return [...accumulated]
    },
    refetchInterval: POLL_INTERVAL,
    staleTime: 0,
  })

  useEffect(() => {
    if (error) logger.error('useSectionHistory: fetch failed', error)
  }, [error])

  return {
    series: data ?? [],
    // Only report stale during key transitions, not regular 2s polls
    stale: isFetching && keyChanged,
  }
}
