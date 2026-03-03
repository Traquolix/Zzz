/**
 * Centralized data hook for the SHM page.
 *
 * Manages selected infrastructure, selected day, and all three async
 * fetches (summary, spectral, peak) with proper AbortController cleanup
 * to prevent race conditions during rapid infrastructure switching.
 */

import { useState, useEffect, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { useKeyboardShortcut } from '@/hooks/useKeyboardShortcuts'
import { logger } from '@/lib/logger'
import { fetchSpectralData, fetchPeakFrequencies, fetchSpectralSummary, fetchSHMStatus } from '@/api/infrastructure'
import { getDayTimeRange } from '@/components/SHM'
import type {
    Infrastructure,
    SelectedInfrastructure,
    SpectralTimeSeries,
    PeakFrequencyData,
    SpectralSummary,
    SHMStatus,
} from '@/types/infrastructure'

export type UseSHMDataReturn = {
    // Selection
    selectedInfrastructure: SelectedInfrastructure | null
    handleSelect: (infra: Infrastructure) => void
    handleDeselect: () => void

    // Day filtering
    dataSummary: SpectralSummary | null
    selectedDay: Date | null
    setSelectedDay: (day: Date | null) => void

    // Spectral data
    spectralData: SpectralTimeSeries | null
    spectralLoading: boolean
    spectralError: string | null

    // Peak data
    peakData: PeakFrequencyData | null
    peakLoading: boolean

    // SHM status
    shmStatus: SHMStatus | null
}

export function useSHMData() {
    const { t } = useTranslation()

    // --- Selection state ---
    const [selectedInfrastructure, setSelectedInfrastructure] =
        useState<SelectedInfrastructure | null>(null)

    // --- Day filtering ---
    const [dataSummary, setDataSummary] = useState<SpectralSummary | null>(null)
    const [selectedDay, setSelectedDay] = useState<Date | null>(null)

    // --- Async data ---
    const [spectralData, setSpectralData] = useState<SpectralTimeSeries | null>(null)
    const [peakData, setPeakData] = useState<PeakFrequencyData | null>(null)
    const [spectralLoading, setSpectralLoading] = useState(false)
    const [peakLoading, setPeakLoading] = useState(false)
    const [spectralError, setSpectralError] = useState<string | null>(null)
    const [shmStatus, setSHMStatus] = useState<SHMStatus | null>(null)

    // --- Callbacks ---

    const handleSelect = useCallback((infra: Infrastructure) => {
        setSelectedInfrastructure({
            id: infra.id,
            name: infra.name,
            type: infra.type,
            fiberId: infra.fiberId,
            startChannel: infra.startChannel,
            endChannel: infra.endChannel,
        })
    }, [])

    const handleDeselect = useCallback(() => {
        setSelectedInfrastructure(null)
    }, [])

    // --- Escape key to deselect ---

    useKeyboardShortcut({
        combo: 'Escape',
        handler: () => {
            if (selectedInfrastructure) {
                setSelectedInfrastructure(null)
            }
        },
        global: true,
    })

    // --- Fetch data summary (available date range) ---

    useEffect(() => {
        if (!selectedInfrastructure) return

        const controller = new AbortController()

        async function loadSummary() {
            try {
                const summary = await fetchSpectralSummary()
                if (!controller.signal.aborted) {
                    setDataSummary(summary)
                    setSelectedDay(null) // Default to "All time"
                }
            } catch (err) {
                if (!controller.signal.aborted) {
                    logger.error('Failed to load spectral summary:', err)
                }
            }
        }
        loadSummary()

        return () => controller.abort()
    }, [selectedInfrastructure])

    // --- Fetch spectral data ---

    useEffect(() => {
        if (!selectedInfrastructure) {
            setSpectralData(null)
            setPeakData(null)
            return
        }

        const controller = new AbortController()

        async function loadSpectralData() {
            setSpectralLoading(true)
            setSpectralError(null)
            try {
                const timeRange = getDayTimeRange(selectedDay)
                const spectra = await fetchSpectralData({
                    maxTimeSamples: 10000,
                    maxFreqBins: 400,
                    startTime: timeRange?.from,
                    endTime: timeRange?.to,
                })
                if (!controller.signal.aborted) {
                    setSpectralData(spectra)
                }
            } catch (err) {
                if (!controller.signal.aborted) {
                    logger.error('Failed to load spectral data:', err)
                    setSpectralError(
                        t('shm.spectralLoadError', 'Failed to load spectral data'),
                    )
                }
            } finally {
                if (!controller.signal.aborted) {
                    setSpectralLoading(false)
                }
            }
        }
        loadSpectralData()

        return () => controller.abort()
    }, [selectedInfrastructure, selectedDay, t])

    // --- Fetch peak data ---

    useEffect(() => {
        if (!selectedInfrastructure) return

        const controller = new AbortController()

        async function loadPeakData() {
            setPeakLoading(true)
            try {
                const timeRange = getDayTimeRange(selectedDay)
                const peaks = await fetchPeakFrequencies({
                    maxSamples: 10000,
                    startTime: timeRange?.from,
                    endTime: timeRange?.to,
                })
                if (!controller.signal.aborted) {
                    setPeakData(peaks)
                }
            } catch (err) {
                if (!controller.signal.aborted) {
                    logger.error('Failed to load peak data:', err)
                }
            } finally {
                if (!controller.signal.aborted) {
                    setPeakLoading(false)
                }
            }
        }
        loadPeakData()

        return () => controller.abort()
    }, [selectedInfrastructure, selectedDay])

    // --- Fetch SHM status ---

    useEffect(() => {
        if (!selectedInfrastructure) {
            setSHMStatus(null)
            return
        }

        const controller = new AbortController()

        async function loadSHMStatus() {
            try {
                if (!selectedInfrastructure) return
                const status = await fetchSHMStatus(selectedInfrastructure.id)
                if (!controller.signal.aborted) {
                    setSHMStatus(status)
                }
            } catch (err) {
                if (!controller.signal.aborted) {
                    logger.error('Failed to load SHM status:', err)
                    setSHMStatus(null)
                }
            }
        }
        loadSHMStatus()

        return () => controller.abort()
    }, [selectedInfrastructure])

    return {
        selectedInfrastructure,
        handleSelect,
        handleDeselect,
        dataSummary,
        selectedDay,
        setSelectedDay,
        spectralData,
        spectralLoading,
        spectralError,
        peakData,
        peakLoading,
        shmStatus,
    }
}
