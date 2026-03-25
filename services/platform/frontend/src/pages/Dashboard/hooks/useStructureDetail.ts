import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import type { SHMStatus, SpectralTimeSeries, PeakFrequencyData, SpectralSummary } from '@/types/infrastructure'
import { fetchSpectralData, fetchPeakFrequencies, fetchSpectralSummary } from '@/api/infrastructure'

export function useStructureDetail(selectedId: string | null, allStatuses: Map<string, SHMStatus>) {
  const shmStatus: SHMStatus | null = (selectedId ? allStatuses.get(selectedId) : undefined) ?? null

  // Spectral data is heavy and static (HDF5) — cache aggressively
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
    gcTime: Infinity,
  })
  const spectralData: SpectralTimeSeries | null = spectraQuery.data ?? null
  const spectralLoading = spectraQuery.isLoading

  // Summary (lightweight metadata) — loaded first so peaks can use its date range
  const summaryQuery = useQuery({
    queryKey: ['shm-summary', selectedId],
    queryFn: () => fetchSpectralSummary({ infrastructureId: selectedId! }),
    enabled: !!selectedId,
    staleTime: Infinity,
    gcTime: Infinity,
  })
  const dataSummary: SpectralSummary | null = summaryQuery.data ?? null

  // Peak frequencies — date range from summary avoids the backend's "default to today" guard
  const peaksQuery = useQuery({
    queryKey: ['shm-peaks', selectedId],
    queryFn: () => {
      if (!selectedId || !dataSummary) throw new Error('invariant: enabled guard failed')
      return fetchPeakFrequencies({
        infrastructureId: selectedId,
        startTime: new Date(dataSummary.t0),
        endTime: new Date(dataSummary.endTime),
      })
    },
    enabled: !!selectedId && !!dataSummary,
    staleTime: Infinity,
    gcTime: Infinity,
  })
  const peakData: PeakFrequencyData | null = peaksQuery.data ?? null
  const peakLoading = peaksQuery.isLoading

  return useMemo(
    () => ({ shmStatus, spectralData, spectralLoading, peakData, peakLoading, dataSummary }),
    [shmStatus, spectralData, spectralLoading, peakData, peakLoading, dataSummary],
  )
}
