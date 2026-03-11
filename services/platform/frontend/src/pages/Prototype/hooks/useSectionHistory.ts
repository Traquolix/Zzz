import { useRef } from 'react'
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
 * Returns `stale: true` while a fetch is in flight (initial load or background refetch).
 */
export function useSectionHistory(sectionId: string, timeRange: string) {
  const { flow } = useRealtime()
  const minutes = TIME_RANGE_MINUTES[timeRange] ?? 5

  const sinceRef = useRef<number | undefined>(undefined)
  const accumulatedRef = useRef<SectionDataPoint[]>([])

  // Track previous query key to reset cursors on change
  const prevKeyRef = useRef(`${sectionId}:${minutes}:${flow}`)

  const { data, isFetching, error } = useQuery({
    queryKey: ['section-history', sectionId, minutes, flow],
    queryFn: async () => {
      const currentKey = `${sectionId}:${minutes}:${flow}`

      // Reset cursors if query key changed (section, time range, or flow)
      if (prevKeyRef.current !== currentKey) {
        sinceRef.current = undefined
        accumulatedRef.current = []
        prevKeyRef.current = currentKey
      }

      const since = sinceRef.current
      const res = await fetchSectionHistory(sectionId, minutes, flow, since)
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

      return [...accumulated]
    },
    refetchInterval: POLL_INTERVAL,
    staleTime: 0,
  })

  if (error) {
    logger.error('useSectionHistory: fetch failed', error)
  }

  return {
    series: data ?? [],
    stale: isFetching,
  }
}
