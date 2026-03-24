import type { PendingPoint } from '../../types'

export const MAP_SOURCES = {
  fibers: 'fibers',
  channelHelper: 'channel-helper',
  vehicles: 'vehicles',
  sectionHighlights: 'section-highlights',
  hoverHighlight: 'hover-highlight',
  pendingSection: 'pending-section',
  pendingPoint: 'pending-point',
  structureLines: 'structure-lines',
  speedSections: 'speed-sections',
} as const

export const MAP_LAYERS = {
  fiberLines: 'fiber-lines',
  channelHelperDots: 'channel-helper-dots',
  sectionHighlight: 'section-highlight-layer',
  hoverHighlightGlow: 'hover-highlight-glow',
  hoverHighlightLine: 'hover-highlight-line',
  vehicleDots: 'vehicle-dots',
  pendingSection: 'pending-section-layer',
  pendingPoint: 'pending-point-layer',
  structureLines: 'structure-lines-layer',
  speedSectionLines: 'speed-section-lines',
  buildings3d: '3d-buildings',
} as const

export interface MapHandlers {
  onIncidentClick?: (id: string) => void
  onMapClick?: () => void
  onFiberClick?: (point: PendingPoint) => void
  onSectionComplete?: (fiberId: string, direction: 0 | 1, startChannel: number, endChannel: number) => void
  onOverviewChange?: (isOverview: boolean) => void
  onChannelClick?: (point: PendingPoint) => void
}
