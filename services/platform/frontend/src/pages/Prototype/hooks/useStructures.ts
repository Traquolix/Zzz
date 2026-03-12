import { useState, useMemo, useEffect, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import type {
  Infrastructure,
  SpectralTimeSeries,
  PeakFrequencyData,
  SpectralSummary,
  SHMStatus,
} from '@/types/infrastructure'
import {
  fetchInfrastructure,
  fetchSHMStatus,
  fetchSpectralData,
  fetchPeakFrequencies,
  fetchSpectralSummary,
} from '@/api/infrastructure'

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

export function useStructures(selectedId: string | null) {
  const [selectedDay, setSelectedDay] = useState<Date | null>(null)

  // Reset selectedDay when structure selection changes
  useEffect(() => {
    setSelectedDay(null)
  }, [selectedId])

  // Infrastructure list
  const { data: structures = [], isLoading: loading } = useQuery({
    queryKey: ['infrastructure'],
    queryFn: fetchInfrastructure,
    staleTime: 60_000,
  })

  // Stable query key for batch statuses (same pattern as useLiveStats)
  const structureIds = useMemo(
    () =>
      structures
        .map(s => s.id)
        .sort()
        .join(','),
    [structures],
  )

  // Stable ref for structures to avoid stale closures in queryFn.
  // queryKey uses structureIds (a string) to control cache invalidation,
  // but queryFn needs the actual array — a closure would capture a stale copy.
  const structuresRef = useRef(structures)
  structuresRef.current = structures

  // Batch-fetch all statuses once structures are loaded
  const { data: allStatuses = new Map<string, SHMStatus>() } = useQuery({
    queryKey: ['shm-statuses', structureIds],
    queryFn: () => fetchAllStatuses(structuresRef.current),
    enabled: structures.length > 0,
    staleTime: 60_000,
  })

  // Derive per-structure status from batch result instead of a separate fetch
  const shmStatus: SHMStatus | null = (selectedId ? allStatuses.get(selectedId) : undefined) ?? null

  // Spectral data (heavy — cached aggressively, static HDF5)
  const spectraQuery = useQuery({
    queryKey: ['shm-spectra', selectedId],
    queryFn: () =>
      fetchSpectralData({
        infrastructureId: selectedId!,
        maxTimeSamples: 500,
        maxFreqBins: 200,
      }),
    enabled: !!selectedId,
    staleTime: Infinity,
  })
  const spectralData: SpectralTimeSeries | null = spectraQuery.data ?? null
  const spectralLoading = spectraQuery.isLoading

  // Summary (lightweight metadata) — loaded first so peaks can use its date range
  const summaryQuery = useQuery({
    queryKey: ['shm-summary', selectedId],
    queryFn: () => fetchSpectralSummary({ infrastructureId: selectedId! }),
    enabled: !!selectedId,
    staleTime: Infinity,
  })
  const dataSummary: SpectralSummary | null = summaryQuery.data ?? null

  // Peak frequencies (heavy — cached aggressively, static HDF5).
  // Pass the full data range from the summary so the backend doesn't
  // apply its "default to today" guard (which returns empty for past data).
  const peaksQuery = useQuery({
    queryKey: ['shm-peaks', selectedId],
    queryFn: () =>
      fetchPeakFrequencies({
        infrastructureId: selectedId!,
        startTime: new Date(dataSummary!.t0),
        endTime: new Date(dataSummary!.endTime),
      }),
    enabled: !!selectedId && !!dataSummary,
    staleTime: Infinity,
  })
  const peakData: PeakFrequencyData | null = peaksQuery.data ?? null
  const peakLoading = peaksQuery.isLoading

  // Memoize return object to keep the same reference when values haven't changed
  return useMemo(
    () => ({
      structures,
      loading,
      allStatuses,
      shmStatus,
      spectralData,
      spectralLoading,
      peakData,
      peakLoading,
      dataSummary,
      selectedDay,
      setSelectedDay,
    }),
    [
      structures,
      loading,
      allStatuses,
      shmStatus,
      spectralData,
      spectralLoading,
      peakData,
      peakLoading,
      dataSummary,
      selectedDay,
    ],
  )
}
