export type Detection = {
  fiberLine: string
  channel: number
  speed: number
  count: number
  nCars: number
  nTrucks: number
  direction: 0 | 1
  timestamp: number
}

/** @deprecated Vehicle counts are now included in Detection (count, nCars, nTrucks). */
export type VehicleCount = {
  fiberLine: string
  channelStart: number
  channelEnd: number
  vehicleCount: number
  timestamp: number // ms since epoch
}
