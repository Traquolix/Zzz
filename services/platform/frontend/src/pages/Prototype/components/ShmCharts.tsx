// Re-export shared utilities so existing consumers don't break
export { computeHourTicks, VIRIDIS } from './shmUtils'

// ── Barrel re-exports ────────────────────────────────────────────────

export { SpectralHeatmapCanvas } from './SpectralHeatmapCanvas'
export { PeakScatterPlot } from './PeakScatterPlot'
export { ComparisonOverlay } from './ComparisonOverlay'
export type { ComparisonMode, FocusMode } from './ComparisonOverlay'
