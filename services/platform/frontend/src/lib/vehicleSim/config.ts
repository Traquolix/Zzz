import type { SimConfig } from './types'
import type { KalmanConfig } from './kalman'

export const DEFAULT_CONFIG: SimConfig = {
  metersPerChannel: 5,
  totalChannels: 500,
  maxLanes: 10,
  segmentWidth: 0.8,

  // Track lifecycle
  fadeOutAfterMs: 6000, // Start fading after 6s without detection
  fadeDurationMs: 3000, // 3s fade out
  confirmationCount: 1, // Need 1 detection to confirm a track
  maxCoastingMs: 10000, // Delete track after 10s without detection

  // Association gating
  gateThreshold: 3.0, // 3 standard deviations (99.7% confidence)
  minGateChannels: 10, // Minimum gate of 10 channels regardless of uncertainty

  // Render smoothing - how fast the visual catches up to the estimated position
  // Lower values = smoother but more lag, higher = snappier but may show corrections
  positionSmoothingFactor: 0.08, // ~12 frames to close 90% of gap at 60fps
  velocitySmoothingFactor: 0.03, // Velocity adapts gradually to avoid jerky speed changes
}

export const DEFAULT_KALMAN_CONFIG: KalmanConfig = {
  // Process noise: how much the true state can randomly deviate from constant-velocity model
  // Tuned for vehicle motion at 10Hz updates
  processNoisePosition: 0.001, // channels² per ms² - accounts for slight speed variations
  processNoiseVelocity: 0.00001, // (channels/ms)² per ms² - vehicles maintain fairly steady speeds

  // Measurement noise: how noisy the DAS sensor readings are
  // Higher values = smoother but slower to correct
  // Lower values = more responsive but potentially jittery
  measurementNoisePosition: 64, // channels² (σ ≈ 8 channels)
  measurementNoiseVelocity: 0.0004, // Trust speed measurements less - they can be noisy

  // Initial uncertainty for new tracks
  initialPositionVariance: 36, // σ ≈ 6 channels - fairly confident in initial position
  initialVelocityVariance: 0.0005, // Moderately uncertain about initial velocity
}
