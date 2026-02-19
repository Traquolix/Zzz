export type DataPoint = {
    timestamp: number
    speed: number
    count: number
    direction: 0 | 1
}

export type LandmarkData = {
    fiberId: string
    channel: number
    name: string
    points: DataPoint[]
}

export type SectionDataPoint = {
    timestamp: number
    speed0: number | null // Direction →
    speed1: number | null // Direction ←
    count0: number
    count1: number
}

export type HoveredPoint = {
    point: DataPoint
    x: number
    y: number
} | null

export type HoveredSectionPoint = {
    speed: number
    timestamp: number
    direction: 0 | 1
    count: number
    x: number
    y: number
} | null

export type LandmarkInfo = {
    fiberId: string
    channel: number
    name: string
    key: string
    lng: number
    lat: number
    favorite: boolean
}

export type DirectionGroup<T> = {
    direction: 0 | 1
    fiberId: string  // directional fiber ID (e.g., "carros:0")
    items: T[]
}

export type FiberGroup<T> = {
    parentFiberId: string  // physical cable ID (e.g., "carros")
    fiberName: string
    directions: DirectionGroup<T>[]
}

export const TIME_WINDOW_MS = 60_000
export const CHANNEL_TOLERANCE = 1
