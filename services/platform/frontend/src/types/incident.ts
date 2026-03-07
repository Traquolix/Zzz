export type IncidentStatus = 'active' | 'acknowledged' | 'investigating' | 'resolved'

export type Incident = {
  id: string
  type: 'slowdown' | 'congestion' | 'accident' | 'anomaly'
  severity: 'low' | 'medium' | 'high' | 'critical'
  fiberLine: string // which fiber
  channel: number // which channel (array index)
  channelEnd?: number
  detectedAt: string
  status: IncidentStatus
  duration?: number // ms, for temporary incidents
  speedBefore?: number | null
  speedDuring?: number | null
  speedDropPercent?: number | null
}

export type IncidentAction = {
  id: string
  fromStatus: IncidentStatus
  toStatus: IncidentStatus
  performedBy: string | null
  note: string
  performedAt: string
}

export type IncidentActionHistory = {
  currentStatus: IncidentStatus
  actions: IncidentAction[]
}

export type SnapshotPoint = {
  time: number // epoch ms
  speed: number | null
  flow: number | null
  occupancy: number | null
}

export type IncidentSnapshot = {
  incidentId: string
  fiberLine: string
  centerChannel: number
  capturedAt: number
  points: SnapshotPoint[]
  complete: boolean
}
