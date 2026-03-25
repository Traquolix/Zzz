import { useMemo, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import type { Infrastructure, SHMStatus } from '@/types/infrastructure'
import { fetchInfrastructure, fetchSHMStatus } from '@/api/infrastructure'

async function fetchAllStatuses(structures: Infrastructure[]): Promise<Map<string, SHMStatus>> {
  const results = await Promise.allSettled(
    structures.map(s => fetchSHMStatus(s.id).then(status => [s.id, status] as const)),
  )
  const map = new Map<string, SHMStatus>()
  for (const r of results) {
    if (r.status === 'fulfilled') map.set(r.value[0], r.value[1])
  }
  return map
}

export type InfrastructureData = ReturnType<typeof useInfrastructure>

export function useInfrastructure() {
  const { data: structures = [], isLoading: loading } = useQuery({
    queryKey: ['infrastructure'],
    queryFn: fetchInfrastructure,
    staleTime: 60_000,
  })

  const structureIds = useMemo(
    () =>
      structures
        .map(s => s.id)
        .sort()
        .join(','),
    [structures],
  )

  const structuresRef = useRef(structures)
  structuresRef.current = structures

  const { data: allStatuses = new Map<string, SHMStatus>() } = useQuery({
    queryKey: ['shm-statuses', structureIds],
    queryFn: () => fetchAllStatuses(structuresRef.current),
    enabled: structures.length > 0,
    staleTime: 60_000,
  })

  return useMemo(() => ({ structures, loading, allStatuses }), [structures, loading, allStatuses])
}
