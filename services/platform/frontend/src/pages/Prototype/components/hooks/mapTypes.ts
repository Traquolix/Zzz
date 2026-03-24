import type { PendingPoint } from '../../types'

export interface MapHandlers {
  onIncidentClick?: (id: string) => void
  onMapClick?: () => void
  onFiberClick?: (point: PendingPoint) => void
  onSectionComplete?: (fiberId: string, direction: 0 | 1, startChannel: number, endChannel: number) => void
  onOverviewChange?: (isOverview: boolean) => void
  onChannelClick?: (point: PendingPoint) => void
}
