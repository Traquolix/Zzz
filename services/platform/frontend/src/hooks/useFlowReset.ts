import { useEffect } from 'react'
import { useRealtime } from '@/hooks/useRealtime'

/**
 * Run a callback whenever the data flow changes (sim ↔ live).
 *
 * Wraps `onFlowChange` from `useRealtime` in a one-liner so hooks
 * that accumulate state (detections, stats, vehicles, etc.) can
 * reset without duplicating the same `useEffect` boilerplate.
 */
export function useFlowReset(resetFn: () => void) {
  const { onFlowChange } = useRealtime()

  useEffect(() => {
    return onFlowChange(resetFn)
    // resetFn is intentionally omitted — callers should pass a stable
    // reference (inline arrow closing over refs, or a useCallback).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [onFlowChange])
}
