export type VehiclePosition = {
  id: string
  fiberId: string // Fiber this vehicle is on (for speed limit lookup)
  position: [number, number, number]
  angle: number
  speed: number // Render speed (visual interpolation)
  detectionSpeed: number // Detection speed (ground truth from sensor)
  channel: number
  direction: 0 | 1
  isDetectionMarker: boolean
  isRawDetection?: boolean // True for raw sensor detections (fading pulses)
  opacity?: number // For fade in/out effects
  trackState?: 'tentative' | 'confirmed' | 'coasting'
  innovation?: number // Correction distance (detection - prediction)
}

export type SelectedVehicle = {
  id: string
  speed: number // Render speed (visual)
  detectionSpeed: number // Detection speed (ground truth)
  channel: number
  direction: 0 | 1
  screenX: number
  screenY: number
}

export type SelectedLandmark = {
  fiberId: string
  channel: number
  lng: number
  lat: number
}

export type SelectedIncident = {
  id: string
  type: 'slowdown' | 'congestion' | 'accident' | 'anomaly'
  severity: 'low' | 'medium' | 'high' | 'critical'
  fiberLine: string
  channel: number
  lng: number
  lat: number
}
