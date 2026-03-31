import type { SectionHistoryPoint } from '@/api/sections'
import { formatTime } from '@/lib/formatters'
import type { SectionDataPoint } from '../types'

/** Map API history points to frontend SectionDataPoint shape. */
export function mapHistoryPoints(points: SectionHistoryPoint[]): SectionDataPoint[] {
  return points.map(p => ({
    time: formatTime(p.time),
    timestamp: p.time,
    speed: Math.round(p.speed),
    flow: p.flow,
    occupancy: p.occupancy,
  }))
}
