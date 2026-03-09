/**
 * Infrastructure types for Structural Health Monitoring (SHM)
 * Infrastructure is like a section but predefined/static - defined by fiber, start/end channels
 */
import type { FiberRange } from './fiber'

export type InfrastructureType = 'bridge' | 'tunnel'

export type Infrastructure = FiberRange & {
  type: InfrastructureType
  name: string
  direction?: number | null // null = both directions
  imageUrl?: string | null
}

/**
 * Legacy single-value frequency reading (for backwards compatibility with simple widgets)
 */
export type FrequencyReading = {
  infrastructureId: string
  frequency: number // Hz - peak frequency
  amplitude: number // Normalized 0-1
  timestamp: number // Unix ms
}

export type SelectedInfrastructure = {
  id: string
  name: string
  type: InfrastructureType
  fiberId: string
  startChannel: number
  endChannel: number
}

/**
 * Full spectral time series data from HDF5.
 * Used for heatmap visualization (time × frequency × power).
 */
export type SpectralTimeSeries = {
  spectra: number[][] // 2D: spectra[timeIndex][freqIndex] = log10(power)
  freqs: number[] // Frequency bin centers (Hz)
  t0: string // ISO timestamp of first sample
  dt: number[] // Time offsets in seconds from t0
  numTimeSamples: number
  numFreqBins: number
  freqRange: [number, number] // [minFreq, maxFreq] in Hz
  durationSeconds: number
}

/**
 * Peak frequency time series for scatter plot visualization.
 */
export type PeakFrequencyData = {
  t0: string // ISO timestamp of first sample
  dt: number[] // Time offsets in seconds from t0
  peakFrequencies: number[] // Peak frequency at each time sample (Hz)
  peakPowers: number[] // Power at peak frequency (log scale)
  freqRange: [number, number] // [minFreq, maxFreq] in Hz
}

/**
 * Summary of available spectral data (lightweight metadata).
 */
export type SpectralSummary = {
  numTimeSamples: number
  numFreqBins: number
  freqRange: [number, number]
  t0: string
  endTime: string
  durationSeconds: number
}

/**
 * SHM status data from the backend.
 */
export type SHMStatus = {
  status: 'nominal' | 'warning' | 'critical'
  currentMean: number
  baselineMean: number
  deviationSigma: number
  direction: string
}
