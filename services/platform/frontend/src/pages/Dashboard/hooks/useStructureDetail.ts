import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import type { SHMStatus, SpectralTimeSeries, PeakFrequencyData, SpectralSummary } from '@/types/infrastructure'
import { fetchSpectralData, fetchPeakFrequencies, fetchSpectralSummary } from '@/api/infrastructure'

export function useStructureDetail(selectedId: string | null, allStatuses: Map<string, SHMStatus>) {
  const shmStatus: SHMStatus | null = (selectedId ? allStatuses.get(selectedId) : undefined) ?? null

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

  const summaryQuery = useQuery({
    queryKey: ['shm-summary', selectedId],
    queryFn: () => fetchSpectralSummary({ infrastructureId: selectedId! }),
    enabled: !!selectedId,
    staleTime: Infinity,
  })
  const dataSummary: SpectralSummary | null = summaryQuery.data ?? null

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

  return useMemo(
    () => ({ shmStatus, spectralData, spectralLoading, peakData, peakLoading, dataSummary }),
    [shmStatus, spectralData, spectralLoading, peakData, peakLoading, dataSummary],
  )
}
