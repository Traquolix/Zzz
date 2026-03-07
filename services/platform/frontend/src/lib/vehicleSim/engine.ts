import type { Track, SensorEvent, SimConfig } from './types'
import type { KalmanConfig } from './kalman'
import { DEFAULT_CONFIG, DEFAULT_KALMAN_CONFIG } from './config'
import { createKalmanState, kalmanPredict, kalmanUpdate, mahalanobisDistance } from './kalman'
import { createCars, speedToChannelsPerMs, lanesForDirection, randomOffset, generateUUID } from './utils'

export class VehicleSimEngine {
  tracks: Track[] = []
  config: SimConfig
  kalmanConfig: KalmanConfig

  // Store recent detections for visualization (raw sensor data)
  recentDetections: Array<{
    channel: number
    direction: 0 | 1
    timestamp: number
    speed: number
  }> = []

  constructor(config: Partial<SimConfig> = {}, kalmanConfig: Partial<KalmanConfig> = {}) {
    this.config = { ...DEFAULT_CONFIG, ...config }
    this.kalmanConfig = { ...DEFAULT_KALMAN_CONFIG, ...kalmanConfig }
  }

  private lastCleanupTime = 0

  /** Clear all tracks and detections (e.g. on data flow switch). */
  reset(): void {
    this.tracks = []
    this.recentDetections = []
    this.lastCleanupTime = 0
  }

  /**
   * Process incoming sensor detection
   */
  onSensorEvent(event: SensorEvent, now: number): void {
    // Store raw detection for visualization
    this.recentDetections.push({
      channel: event.channel,
      direction: event.direction,
      timestamp: now,
      speed: event.speed,
    })

    // Find best matching track using Mahalanobis distance
    const match = this.findBestMatch(event)

    if (match) {
      this.updateTrack(match, event, now)
    } else {
      this.createTrack(event, now)
    }

    // Cleanup old detections periodically (not on every event)
    // Only cleanup every 500ms to reduce GC pressure
    if (now - this.lastCleanupTime > 500) {
      this.lastCleanupTime = now
      const cutoff = now - 2000
      // In-place removal from the front (detections are chronological)
      let removeCount = 0
      for (let i = 0; i < this.recentDetections.length; i++) {
        if (this.recentDetections[i].timestamp >= cutoff) break
        removeCount++
      }
      if (removeCount > 0) {
        this.recentDetections.splice(0, removeCount)
      }
    }
  }

  /**
   * Advance simulation by deltaMs - called every frame
   */
  tick(now: number, deltaMs: number): void {
    for (const track of this.tracks) {
      // Kalman prediction step: extrapolate estimated position
      track.kalman = kalmanPredict(track.kalman, deltaMs, this.kalmanConfig)

      // Smooth rendering interpolation: render position chases kalman position
      this.updateRenderState(track, deltaMs)

      // Update track state based on time since last detection
      this.updateTrackState(track, now)

      // Update visual opacities
      this.updateOpacities(track, now, deltaMs)

      // Check bounds (use render position for smoother exit)
      this.checkBounds(track)
    }

    // Remove dead tracks (in-place to avoid array allocation every frame)
    for (let i = this.tracks.length - 1; i >= 0; i--) {
      if (this.tracks[i].opacity <= 0) {
        this.tracks.splice(i, 1)
      }
    }
  }

  /**
   * Smoothly interpolate render state toward Kalman state
   * This prevents rubber-banding by making corrections gradual
   */
  private updateRenderState(track: Track, deltaMs: number): void {
    // Calculate adaptive smoothing based on frame time
    // This ensures consistent smoothing regardless of frame rate
    const frameRatio = deltaMs / 16.67 // Normalize to 60fps
    const posFactor = 1 - Math.pow(1 - this.config.positionSmoothingFactor, frameRatio)
    const velFactor = 1 - Math.pow(1 - this.config.velocitySmoothingFactor, frameRatio)

    // Exponential smoothing toward Kalman state
    const positionError = track.kalman.position - track.renderPosition
    const velocityError = track.kalman.velocity - track.renderVelocity

    // Update render velocity first (it drives position)
    track.renderVelocity += velocityError * velFactor

    // Move render position by render velocity, then add position correction
    track.renderPosition += track.renderVelocity * deltaMs
    track.renderPosition += positionError * posFactor
  }

  /**
   * Find the best matching track for a detection using Mahalanobis gating
   */
  private findBestMatch(event: SensorEvent): Track | undefined {
    let bestTrack: Track | undefined
    let bestDistance = Infinity

    for (const track of this.tracks) {
      const distance = mahalanobisDistance(track.kalman, event.channel, event.direction, track.direction)

      // Check if within gate and better than previous best
      if (distance < this.config.gateThreshold && distance < bestDistance) {
        // Also check minimum gate (floor)
        const positionDiff = Math.abs(event.channel - track.kalman.position)
        const uncertainty = Math.sqrt(track.kalman.positionVariance)
        const effectiveGate = Math.max(uncertainty * this.config.gateThreshold, this.config.minGateChannels)

        if (positionDiff < effectiveGate) {
          bestDistance = distance
          bestTrack = track
        }
      }
    }

    return bestTrack
  }

  /**
   * Update an existing track with a new detection
   */
  private updateTrack(track: Track, event: SensorEvent, now: number): void {
    // Store pre-update position for visualization
    const predictedPosition = track.kalman.position
    track.lastDetectionChannel = event.channel
    track.lastDetectionSpeed = event.speed // Store raw detection speed (ground truth)
    track.lastInnovation = event.channel - predictedPosition

    // Convert speed to channels/ms for Kalman update
    const velocityChannelsPerMs = speedToChannelsPerMs(event.speed, this.config.metersPerChannel)
    const signedVelocity = track.direction === 0 ? velocityChannelsPerMs : -velocityChannelsPerMs

    // Kalman update step: incorporate measurement
    track.kalman = kalmanUpdate(track.kalman, event.channel, signedVelocity, this.kalmanConfig)

    // Update track metadata
    track.lastDetectionTime = now
    track.detectionCount++

    // Promote tentative tracks after enough detections
    if (track.state === 'tentative' && track.detectionCount >= this.config.confirmationCount) {
      track.state = 'confirmed'
    }

    // Coasting tracks become confirmed again when they get a detection
    if (track.state === 'coasting') {
      track.state = 'confirmed'
    }

    // Reset opacity for confirmed tracks
    if (track.state === 'confirmed') {
      track.opacity = 1
    }

    // Handle count changes (add/remove cars)
    this.reconcileCars(track, event.count)
  }

  /**
   * Create a new track from a detection
   */
  private createTrack(event: SensorEvent, now: number): void {
    const velocityChannelsPerMs = speedToChannelsPerMs(event.speed, this.config.metersPerChannel)
    const signedVelocity = event.direction === 0 ? velocityChannelsPerMs : -velocityChannelsPerMs

    const track: Track = {
      id: generateUUID(),
      kalman: createKalmanState(event.channel, signedVelocity, this.kalmanConfig),
      direction: event.direction,
      state: 'tentative',
      opacity: 0, // Fade in
      createdAt: now,
      lastDetectionTime: now,
      detectionCount: 1,
      cars: createCars(event.count, event.direction, this.config),
      recentCounts: [event.count],
      // Initialize render state to match kalman state
      renderPosition: event.channel,
      renderVelocity: signedVelocity,
      lastDetectionChannel: event.channel,
      lastDetectionSpeed: event.speed, // Store initial detection speed
      lastInnovation: 0,
    }

    this.tracks.push(track)
  }

  /**
   * Update track lifecycle state based on time
   */
  private updateTrackState(track: Track, now: number): void {
    const timeSinceDetection = now - track.lastDetectionTime

    if (track.state === 'confirmed' && timeSinceDetection > this.config.fadeOutAfterMs) {
      track.state = 'coasting'
    }

    // Tentative tracks that don't get confirmed quickly should be deleted
    if (track.state === 'tentative' && timeSinceDetection > 1000) {
      track.opacity = 0 // Will be filtered out
    }
  }

  /**
   * Add or remove cars to match the detection count
   */
  private reconcileCars(track: Track, count: number): void {
    track.recentCounts.push(count)
    if (track.recentCounts.length > 5) track.recentCounts.shift()

    const targetCount = this.medianCount(track.recentCounts)
    const activeCount = track.cars.filter(c => c.state === 'active').length

    if (targetCount > activeCount) {
      this.addCars(track, targetCount - activeCount)
    } else if (targetCount < activeCount) {
      this.removeCars(track, activeCount - targetCount)
    }
  }

  private addCars(track: Track, count: number): void {
    const usedLanes = new Set(track.cars.filter(c => c.state === 'active').map(c => c.lane))
    const available = lanesForDirection(track.direction).filter(l => !usedLanes.has(l))

    for (let i = 0; i < Math.min(count, available.length); i++) {
      track.cars.push({
        id: generateUUID(),
        lane: available[i],
        offset: randomOffset(this.config.segmentWidth),
        opacity: 0,
        state: 'active',
      })
    }
  }

  private removeCars(track: Track, count: number): void {
    const active = track.cars.filter(c => c.state === 'active').sort((a, b) => b.lane - a.lane)
    for (let i = 0; i < Math.min(count, active.length); i++) {
      active[i].state = 'fading-out'
    }
  }

  private medianCount(counts: number[]): number {
    if (counts.length === 0) return 1
    const sorted = [...counts].sort((a, b) => a - b)
    const mid = Math.floor(sorted.length / 2)
    return sorted.length % 2 ? sorted[mid] : Math.round((sorted[mid - 1] + sorted[mid]) / 2)
  }

  private updateOpacities(track: Track, _now: number, deltaMs: number): void {
    // Track opacity
    if (track.state === 'tentative') {
      // Tentative tracks fade in slowly
      track.opacity = Math.min(0.5, track.opacity + deltaMs / 1000)
    } else if (track.state === 'confirmed') {
      // Confirmed tracks are fully visible
      track.opacity = Math.min(1, track.opacity + deltaMs / 300)
    } else if (track.state === 'coasting') {
      // Coasting tracks fade out
      track.opacity = Math.max(0, track.opacity - deltaMs / this.config.fadeDurationMs)
    }

    // Car opacities
    for (const car of track.cars) {
      if (car.state === 'active' && car.opacity < 1) {
        car.opacity = Math.min(1, car.opacity + deltaMs / 400)
      }
      if (car.state === 'fading-out') {
        car.opacity = Math.max(0, car.opacity - deltaMs / 400)
      }
    }
    track.cars = track.cars.filter(c => c.opacity > 0 || c.state === 'active')
  }

  private checkBounds(track: Track): void {
    // Use render position for bounds check (smoother exit)
    if (track.renderPosition < -50 || track.renderPosition > this.config.totalChannels + 50) {
      track.opacity = 0
    }
  }

  /**
   * Get current channel position for rendering
   * Uses smoothed render position (not raw Kalman) for visual smoothness
   */
  getTrackPosition(track: Track): number {
    return track.renderPosition
  }

  /**
   * Get current speed in km/h for rendering (visual speed)
   * Uses smoothed render velocity for consistency with position
   */
  getRenderSpeed(track: Track): number {
    const absVelocity = Math.abs(track.renderVelocity)
    // Convert channels/ms back to km/h
    return absVelocity * this.config.metersPerChannel * 1000 * 3.6
  }

  /**
   * Get detection speed in km/h (ground truth from sensor)
   * This is the raw speed from the last detection attributed to this track
   */
  getDetectionSpeed(track: Track): number {
    return track.lastDetectionSpeed
  }
}
