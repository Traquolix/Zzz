import { useQuery } from '@tanstack/react-query'
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

const formatTime = (d: Date) =>
  d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })

function formatSnapshot(snapshot: IncidentSnapshot): FormattedSnapshotPoint[] {
  return snapshot.points.map(p => ({
    time: formatTime(new Date(p.time)),
    speed: p.speed ?? undefined,
    flow: p.flow ?? undefined,
    occupancy: p.occupancy ?? undefined,
  }))
}

/**
 * Fetch and poll an incident snapshot until it's complete.
 *
 * Polls every 1s while `complete` is false. Auto-pauses on hidden tabs.
 * Cancels on unmount or when `incidentId`/`flow` changes.
 */
export function useIncidentSnapshot(incidentId: string, flow: DataFlow): UseIncidentSnapshotResult {
  const { data, isLoading } = useQuery({
    queryKey: ['incident-snapshot', incidentId, flow],
    queryFn: () => fetchIncidentSnapshot(incidentId, flow),
    refetchInterval: query => {
      if (query.state.data?.complete) return false
      return 1000
    },
    staleTime: 0,
  })

  const complete = data?.complete ?? false
  const points = data ? formatSnapshot(data) : null

  return { points, loading: isLoading, complete }
}
