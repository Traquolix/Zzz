/**
 * Base type for entities that occupy a range of channels on a fiber.
 * Shared by Infrastructure and other channel-range entities.
 */
export type FiberRange = {
  id: string
  fiberId: string
  startChannel: number
  endChannel: number
}

export type FiberLine = {
  id: string // e.g. "carros:0" (directional fiber ID)
  parentFiberId: string // e.g. "carros" (physical cable ID)
  direction: 0 | 1
  name: string
  color: string
  coordinates: [number, number][] // [lng, lat], index = channel/sensor (may be directional if precomputed)
  baseCoordinates?: ([number, number] | [null, null])[] // Original fiber center-line coordinates
  coordsPrecomputed?: boolean // true = coordinates already include directional offset, don't apply on frontend
  landmarks?: { channel: number; name: string }[]
  calibration?: { channel: number; data: unknown }[] // define shape when needed
}
