export type IncidentType = 'accident' | 'congestion' | 'slowdown' | 'anomaly'
export type IncidentStatus = 'active' | 'acknowledged' | 'investigating' | 'resolved'

export type Incident = {
  id: string
  type: IncidentType
  tags: string[]
  fiberId: string
  direction: 0 | 1
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
export type DisplayIncident = Incident & {
  title: string
  description: string
  location: [number, number]
  resolved: boolean
}

export type CalendarDay = {
  date: string
  count: number
  hasUnresolved?: boolean
  hasUnread?: boolean
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
  direction: 0 | 1
  centerChannel: number
  capturedAt: number
  points: SnapshotPoint[]
  complete: boolean
}
