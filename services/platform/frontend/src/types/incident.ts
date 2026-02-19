export type Incident = {
    id: string
    type: 'slowdown' | 'congestion' | 'accident' | 'anomaly'
    severity: 'low' | 'medium' | 'high' | 'critical'
    fiberLine: string      // which fiber
    channel: number        // which channel (array index)
    detectedAt: string
    status: 'active' | 'resolved'
    duration?: number      // ms, for temporary incidents
}

export type BufferedDetection = {
    fiberLine: string
    channel: number
    speed: number
    count: number
    direction: 0 | 1
    timestamp: number
}

export type IncidentSnapshot = {
    incidentId: string
    fiberLine: string
    centerChannel: number
    capturedAt: number
    detections: BufferedDetection[]
}