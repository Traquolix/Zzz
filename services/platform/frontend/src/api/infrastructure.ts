import { apiRequest } from './client'
import type { Infrastructure, SpectralTimeSeries, PeakFrequencyData, SpectralSummary } from '@/types/infrastructure'

/**
 * Fetch all infrastructure items
 */
export async function fetchInfrastructure(): Promise<Infrastructure[]> {
    return apiRequest<Infrastructure[]>('/api/infrastructure')
}

/**
 * Fetch spectral time series data for heatmap visualization.
 *
 * In production mode, data is fetched for the specified infrastructureId.
 * In demo mode (no infrastructureId), sample data is returned.
 */
export async function fetchSpectralData(options?: {
    infrastructureId?: string
    maxTimeSamples?: number
    maxFreqBins?: number
    startIdx?: number
    endIdx?: number
    startTime?: Date
    endTime?: Date
}): Promise<SpectralTimeSeries> {
    const params = new URLSearchParams()
    // infrastructureId will be used in production for real-time data
    if (options?.infrastructureId) params.set('infrastructureId', options.infrastructureId)
    if (options?.maxTimeSamples) params.set('maxTimeSamples', String(options.maxTimeSamples))
    if (options?.maxFreqBins) params.set('maxFreqBins', String(options.maxFreqBins))
    if (options?.startIdx !== undefined) params.set('startIdx', String(options.startIdx))
    if (options?.endIdx !== undefined) params.set('endIdx', String(options.endIdx))
    if (options?.startTime) params.set('startTime', options.startTime.toISOString())
    if (options?.endTime) params.set('endTime', options.endTime.toISOString())

    const query = params.toString()
    return apiRequest<SpectralTimeSeries>(`/api/shm/spectra${query ? `?${query}` : ''}`)
}

/**
 * Fetch peak frequency data for scatter plot visualization.
 *
 * In production mode, data is fetched for the specified infrastructureId.
 * In demo mode (no infrastructureId), sample data is returned.
 */
export async function fetchPeakFrequencies(options?: {
    infrastructureId?: string
    maxSamples?: number
    startTime?: Date
    endTime?: Date
}): Promise<PeakFrequencyData> {
    const params = new URLSearchParams()
    // infrastructureId will be used in production for real-time data
    if (options?.infrastructureId) params.set('infrastructureId', options.infrastructureId)
    if (options?.maxSamples) params.set('maxSamples', String(options.maxSamples))
    if (options?.startTime) params.set('startTime', options.startTime.toISOString())
    if (options?.endTime) params.set('endTime', options.endTime.toISOString())

    const query = params.toString()
    return apiRequest<PeakFrequencyData>(`/api/shm/peaks${query ? `?${query}` : ''}`)
}

/**
 * Fetch spectral data summary (lightweight metadata).
 */
export async function fetchSpectralSummary(): Promise<SpectralSummary> {
    return apiRequest<SpectralSummary>('/api/shm/summary')
}
