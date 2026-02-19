export type FiberLine = {
    id: string                      // e.g. "carros:0" (directional fiber ID)
    parentFiberId: string           // e.g. "carros" (physical cable ID)
    direction: 0 | 1
    name: string
    color: string
    coordinates: [number, number][] // [lng, lat], index = channel/sensor
    coordsPrecomputed?: boolean     // true = coordinates already include directional offset, don't apply on frontend
    landmarks?: { channel: number; name: string }[]
    calibration?: { channel: number; data: unknown }[]  // define shape when needed
}
