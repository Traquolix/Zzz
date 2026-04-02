import type { KalmanState } from './kalman'

export type Car = {
  id: string
  lane: number
  offset: number
  opacity: number
  state: 'active' | 'fading-out'
}

/**
 * Track lifecycle states:
 * - tentative: New track, needs confirmation (2+ detections)
 * - confirmed: Reliable track with recent detections
 * - coasting: No recent detections, relying on prediction
 */
export type TrackState = 'tentative' | 'confirmed' | 'coasting'

export type Track = {
  id: string
  kalman: KalmanState // Position/velocity estimation (truth estimate)
  direction: 0 | 1
  state: TrackState
  opacity: number
  createdAt: number
  lastDetectionTime: number
  detectionCount: number // Total detections matched to this track
  cars: Car[]
  recentCounts: number[]

  // Smooth rendering state (interpolates toward kalman state)
  renderPosition: number // Current rendered position (smoothly follows kalman)
  renderVelocity: number // Current rendered velocity (smoothly follows kalman)

  // For visualization/debugging
  lastDetectionChannel: number // Raw detection position (before Kalman update)
  lastDetectionSpeed: number // Raw detection speed in km/h (ground truth)
  lastInnovation: number // Correction applied (detection - prediction)
  lastGlrtMax: number // Max GLRT correlation value
  lastStrainPeak: number // Peak strain rate amplitude
  lastStrainRms: number // RMS strain rate energy
  lastNTrucks: number // Truck count from last detection
}

export type SensorEvent = {
  channel: number
  speed: number
  count: number
  direction: 0 | 1
  glrtMax: number
  strainPeak: number
  strainRms: number
  nTrucks: number
}

export type SimConfig = {
  metersPerChannel: number
  totalChannels: number
  maxLanes: number
  segmentWidth: number

  // Track lifecycle
  fadeOutAfterMs: number // Start fading after no detection for this long
  fadeDurationMs: number // How long fade takes
  confirmationCount: number // Detections needed to confirm a tentative track
  maxCoastingMs: number // Max time to coast before deletion

  // Association gating
  gateThreshold: number // Mahalanobis distance threshold (typically 3.0)
  minGateChannels: number // Minimum gate size in channels (floor)

  // Render smoothing
  positionSmoothingFactor: number // How fast render position catches up to kalman (0-1, higher = faster)
  velocitySmoothingFactor: number // How fast render velocity catches up to kalman (0-1, higher = faster)
}
