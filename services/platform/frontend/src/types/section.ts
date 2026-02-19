export type FiberSection = {
    id: string              // `section:${fiberId}:${start}-${end}`
    fiberId: string
    startChannel: number
    endChannel: number
    name: string
    color?: string
    favorite?: boolean
}

export type PendingSectionPoint = {
    fiberId: string
    channel: number
    lng: number
    lat: number
} | null

export type LayerVisibility = {
    cables: boolean
    fibers: boolean
    vehicles: boolean
    heatmap: boolean
    landmarks: boolean
    sections: boolean
    detections: boolean
    incidents: boolean
    infrastructure: boolean
}

export type SelectedSection = {
    sectionId: string
    fiberId: string
}

// For dragging section endpoints
export type DraggingEndpoint = {
    sectionId: string
    endpoint: 'start' | 'end'
} | null
