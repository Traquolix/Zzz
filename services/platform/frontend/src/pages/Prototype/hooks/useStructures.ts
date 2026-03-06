import { useState, useEffect, useRef } from 'react'
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

export function useStructures(selectedId: string | null) {
  const [structures, setStructures] = useState<Infrastructure[]>([])
  const [loading, setLoading] = useState(true)

  const [allStatuses, setAllStatuses] = useState<Map<string, SHMStatus>>(new Map())
  const [shmStatus, setShmStatus] = useState<SHMStatus | null>(null)
  const [spectralData, setSpectralData] = useState<SpectralTimeSeries | null>(null)
  const [spectralLoading, setSpectralLoading] = useState(false)
  const [peakData, setPeakData] = useState<PeakFrequencyData | null>(null)
  const [peakLoading, setPeakLoading] = useState(false)
  const [dataSummary, setDataSummary] = useState<SpectralSummary | null>(null)
  const [selectedDay, setSelectedDay] = useState<Date | null>(null)

  const abortRef = useRef<AbortController | null>(null)

  // Fetch infrastructure list on mount, then batch-fetch all statuses
  useEffect(() => {
    let cancelled = false
    setLoading(true)
    fetchInfrastructure()
      .then(data => {
        if (cancelled) return
        setStructures(data)
        // Batch-fetch SHM status for each structure
        Promise.allSettled(data.map(s => fetchSHMStatus(s.id).then(status => [s.id, status] as const))).then(
          results => {
            if (cancelled) return
            const map = new Map<string, SHMStatus>()
            for (const r of results) {
              if (r.status === 'fulfilled') {
                map.set(r.value[0], r.value[1])
              }
            }
            setAllStatuses(map)
          },
        )
      })
      .catch(() => {
        /* API may not be available */
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  // Fetch detail data when selectedId changes
  useEffect(() => {
    // Cancel previous requests
    abortRef.current?.abort()
    abortRef.current = new AbortController()

    if (!selectedId) {
      setShmStatus(null)
      setSpectralData(null)
      setPeakData(null)
      setDataSummary(null)
      setSelectedDay(null)
      return
    }

    let cancelled = false

    // SHM status
    fetchSHMStatus(selectedId)
      .then(data => {
        if (!cancelled) setShmStatus(data)
      })
      .catch(() => {
        if (!cancelled) setShmStatus(null)
      })

    // Spectral data (demo mode — no infrastructureId, the backend serves sample HDF5 data)
    setSpectralLoading(true)
    fetchSpectralData()
      .then(data => {
        if (!cancelled) setSpectralData(data)
      })
      .catch(() => {
        if (!cancelled) setSpectralData(null)
      })
      .finally(() => {
        if (!cancelled) setSpectralLoading(false)
      })

    // Peak frequencies (demo mode)
    setPeakLoading(true)
    fetchPeakFrequencies()
      .then(data => {
        if (!cancelled) setPeakData(data)
      })
      .catch(() => {
        if (!cancelled) setPeakData(null)
      })
      .finally(() => {
        if (!cancelled) setPeakLoading(false)
      })

    // Summary
    fetchSpectralSummary()
      .then(data => {
        if (!cancelled) setDataSummary(data)
      })
      .catch(() => {
        if (!cancelled) setDataSummary(null)
      })

    return () => {
      cancelled = true
      abortRef.current?.abort()
    }
  }, [selectedId])

  return {
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
  }
}
