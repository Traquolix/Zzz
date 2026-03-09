import type { SectionHistoryPoint } from '@/api/sections'
import type { SectionDataPoint } from '../types'

/** Map API history points to frontend SectionDataPoint shape. */
export function mapHistoryPoints(points: SectionHistoryPoint[]): SectionDataPoint[] {
  return points.map(p => ({
    time: new Date(p.time).toLocaleTimeString([], {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    }),
    timestamp: p.time,
    speed: Math.round(p.speed),
    flow: p.flow,
    occupancy: p.occupancy,
  }))
}
