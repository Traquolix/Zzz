export type IncidentType = 'accident' | 'congestion' | 'slowdown' | 'anomaly'
export type Severity = 'critical' | 'high' | 'medium' | 'low'
export type IncidentStatus = 'active' | 'acknowledged' | 'investigating' | 'resolved'

export type Incident = {
  id: string
  type: IncidentType
  severity: Severity
  fiberId: string
  direction: number
  channel: number // which channel (array index)
  channelEnd?: number
  detectedAt: string
  status: IncidentStatus
  duration?: number // ms, for temporary incidents
  speedBefore?: number | null
  speedDuring?: number | null
  speedDropPercent?: number | null
}

/** Enriched incident with display fields computed from fiber geometry. */
export type ProtoIncident = Incident & {
  title: string
  description: string
  location: [number, number]
  resolved: boolean
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
  fiberId: string
  direction: number
  centerChannel: number
  capturedAt: number
  points: SnapshotPoint[]
  complete: boolean
}
