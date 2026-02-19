export type Detection = {
    fiberLine: string
    channel: number
    speed: number
    count: number
    direction: 0 | 1
    timestamp: number
}

/** AI-derived vehicle flow count for a fiber section. */
export type VehicleCount = {
    fiberLine: string
    channelStart: number
    channelEnd: number
    vehicleCount: number
    timestamp: number // ms since epoch
}