import type { FiberSection, LayerVisibility } from './section'
import type { SpeedLimitZone } from './speedLimit'

export type StoredLandmark = {
    fiberId: string
    channel: number
    name: string
    favorite?: boolean
}

export type LayoutItem = {
    i: string
    x: number
    y: number
    w: number
    h: number
}

export type DashboardPreferences = {
    layouts?: Record<string, LayoutItem[]>
    widgets?: string[]
}

export type MapPreferences = {
    landmarks?: StoredLandmark[]
    sections?: FiberSection[]
    layerVisibility?: LayerVisibility
    speedLimitZones?: SpeedLimitZone[]
}

export type UserPreferences = {
    dashboard?: DashboardPreferences
    map?: MapPreferences
}
