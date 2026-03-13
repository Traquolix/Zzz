import { useRef, useState, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { fetchSectionHistory } from '@/api/sections'
import { useRealtime } from '@/hooks/useRealtime'
import { logger } from '@/lib/logger'
import type { SectionDataPoint } from '../types'
import { mapHistoryPoints } from './mapHistoryPoints'

const POLL_INTERVAL = 1000

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
 * At the default 1m range, reuses data from the page-level batch poll
 * (useLiveStats) to avoid a redundant HTTP request and keep stats cards
 * and the chart perfectly synchronized.
 *
 * At longer ranges (5m/15m/1h), fetches independently since the batch
 * poll only covers 1 minute.
 *
 * React Query's refetchInterval auto-pauses when the tab is hidden.
 * Returns `stale: true` while awaiting the first fetch after a range/flow change,
 * NOT during regular background polls.
 */
export function useSectionHistory(sectionId: string, timeRange: string, liveSeries?: SectionDataPoint[]) {
  const { flow } = useRealtime()
  const minutes = TIME_RANGE_MINUTES[timeRange] ?? 5

  // At 1m, reuse the batch data from useLiveStats — no own fetch needed.
  const usesBatchData = minutes === 1 && liveSeries != null

  const sinceRef = useRef<number | undefined>(undefined)
  const accumulatedRef = useRef<SectionDataPoint[]>([])
  const [series, setSeries] = useState<SectionDataPoint[]>([])

  // Stale flag: true only during key transitions (range/flow/section change),
  // NOT during regular background polls (which would cause flicker).
  // Uses useState (not useRef) so changes trigger a re-render.
  // Initialized to true so the spinner shows on first mount.
  const [keyChanged, setKeyChanged] = useState(true)

  // Reset cursors on key change.
  useEffect(() => {
    sinceRef.current = undefined
    accumulatedRef.current = []
    setSeries([])
    setKeyChanged(true)
  }, [sectionId, minutes, flow])

  // When using batch data, sync series directly from liveSeries.
  useEffect(() => {
    if (!usesBatchData || !liveSeries) return
    setSeries(liveSeries)
    setKeyChanged(false)
  }, [usesBatchData, liveSeries])

  // queryFn fetches and eagerly advances the since cursor so the next poll
  // (which may fire before the useEffect runs) never resends stale cursors.
  // Ref writes are safe here — they don't trigger renders or affect React state.
  const {
    data: rawResponse,
    isFetching,
    dataUpdatedAt,
    error,
  } = useQuery({
    queryKey: ['section-history', sectionId, minutes, flow],
    queryFn: async () => {
      const res = await fetchSectionHistory(sectionId, minutes, flow, sinceRef.current)
      if (res.points.length > 0) {
        sinceRef.current = res.points[res.points.length - 1].time
      }
      return res
    },
    refetchInterval: POLL_INTERVAL,
    staleTime: 0,
    enabled: !usesBatchData,
  })

  // Accumulate, trim, and update cursors outside queryFn.
  // dataUpdatedAt changes on every successful fetch, so this fires reliably.
  useEffect(() => {
    if (usesBatchData) return
    if (!rawResponse) return

    const newPoints = mapHistoryPoints(rawResponse.points)

    let accumulated = accumulatedRef.current
    if (sinceRef.current == null) {
      accumulated = newPoints
    } else if (newPoints.length > 0) {
      accumulated = [...accumulated, ...newPoints]
    }

    // Trim to window
    const cutoff = Date.now() - minutes * 60 * 1000
    const firstValid = accumulated.findIndex(p => p.timestamp >= cutoff)
    if (firstValid > 0) accumulated = accumulated.slice(firstValid)

    accumulatedRef.current = accumulated

    setSeries([...accumulated])
    setKeyChanged(false)
  }, [dataUpdatedAt]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (error) logger.error('useSectionHistory: fetch failed', error)
  }, [error])

  return {
    series,
    // Only report stale during key transitions, not regular polls
    stale: usesBatchData ? false : isFetching && keyChanged,
  }
}
