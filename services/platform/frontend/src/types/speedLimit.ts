import type { FiberRange } from './fiber'

export type SpeedLimitZone = FiberRange & {
  limit: number // km/h
}
