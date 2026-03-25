import { useState, useEffect, useRef } from 'react'
import type { IncidentSnapshot } from '@/types/incident'
import { fetchIncidentSnapshot } from '@/api/incidents'
import type { DataFlow } from '@/context/RealtimeContext'

type FormattedSnapshotPoint = {
  time: string
  speed?: number
  flow?: number
  occupancy?: number
}

type UseIncidentSnapshotResult = {
  points: FormattedSnapshotPoint[] | null
  loading: boolean
  complete: boolean
}

/**
 * Fetch and poll an incident snapshot until it's complete.
 *
 * Polls every 1s while `complete` is false. Cancels on unmount
 * or when `incidentId`/`flow` changes (stale-request safe).
 */
export function useIncidentSnapshot(incidentId: string, flow: DataFlow): UseIncidentSnapshotResult {
  const [points, setPoints] = useState<FormattedSnapshotPoint[] | null>(null)
  const [loading, setLoading] = useState(false)
  const [complete, setComplete] = useState(false)
  const cancelledRef = useRef(false)

  useEffect(() => {
    cancelledRef.current = false
    let timer: ReturnType<typeof setTimeout> | null = null

    const formatTime = (d: Date) =>
      d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })

    const poll = () => {
      fetchIncidentSnapshot(incidentId, flow)
        .then((snapshot: IncidentSnapshot) => {
          if (cancelledRef.current) return
          const mapped = snapshot.points.map(p => ({
            time: formatTime(new Date(p.time)),
            speed: p.speed ?? undefined,
            flow: p.flow ?? undefined,
            occupancy: p.occupancy ?? undefined,
          }))
          setPoints(mapped)
          setComplete(snapshot.complete)
          setLoading(false)
          if (!snapshot.complete) {
            timer = setTimeout(poll, 1000)
          }
        })
        .catch(() => {
          if (cancelledRef.current) return
          setPoints(null)
          setLoading(false)
        })
    }

    setLoading(true)
    setComplete(false)
    poll()

    return () => {
      cancelledRef.current = true
      if (timer) clearTimeout(timer)
    }
  }, [incidentId, flow])

  return { points, loading, complete }
}
