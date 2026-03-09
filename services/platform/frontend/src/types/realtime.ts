export type Detection = {
  fiberId: string
  direction: 0 | 1
  channel: number
  speed: number
  count: number
  nCars: number
  nTrucks: number
  timestamp: number
}

/** @deprecated Vehicle counts are now included in Detection (count, nCars, nTrucks). */
export type VehicleCount = {
  fiberId: string
  direction: 0 | 1
  channelStart: number
  channelEnd: number
  vehicleCount: number
  timestamp: number // ms since epoch
}
