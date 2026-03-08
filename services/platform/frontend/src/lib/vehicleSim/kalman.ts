/**
 * 1D Kalman Filter for vehicle tracking along a fiber
 *
 * State: [position (channel), velocity (channels/ms)]
 *
 * This provides optimal estimation of position and velocity given noisy
 * sensor measurements arriving at ~10Hz.
 */

export type KalmanState = {
  position: number // Estimated channel position
  velocity: number // Estimated velocity in channels/ms
  positionVariance: number // Uncertainty in position (σ²)
  velocityVariance: number // Uncertainty in velocity (σ²)
}

export type KalmanConfig = {
  processNoisePosition: number // How much position can randomly change per ms²
  processNoiseVelocity: number // How much velocity can randomly change per ms²
  measurementNoisePosition: number // Sensor noise in channel measurement (σ²)
  measurementNoiseVelocity: number // Sensor noise in speed measurement (σ²)
  initialPositionVariance: number // Starting uncertainty for new tracks
  initialVelocityVariance: number // Starting uncertainty for new tracks
}

/**
 * Create initial Kalman state from a detection
 */
export function createKalmanState(position: number, velocityChannelsPerMs: number, config: KalmanConfig): KalmanState {
  return {
    position,
    velocity: velocityChannelsPerMs,
    positionVariance: config.initialPositionVariance,
    velocityVariance: config.initialVelocityVariance,
  }
}

/**
 * Predict step: extrapolate state forward in time
 * Called every frame to move the vehicle smoothly
 */
export function kalmanPredict(state: KalmanState, deltaMs: number, config: KalmanConfig): KalmanState {
  // State prediction: position moves by velocity * time
  const predictedPosition = state.position + state.velocity * deltaMs
  const predictedVelocity = state.velocity // Assume constant velocity

  // Uncertainty grows over time (process noise)
  // The longer since last measurement, the less certain we are
  const predictedPositionVariance =
    state.positionVariance + state.velocityVariance * deltaMs * deltaMs + config.processNoisePosition * deltaMs

  const predictedVelocityVariance = state.velocityVariance + config.processNoiseVelocity * deltaMs

  return {
    position: predictedPosition,
    velocity: predictedVelocity,
    positionVariance: predictedPositionVariance,
    velocityVariance: predictedVelocityVariance,
  }
}

/**
 * Update step: incorporate a new measurement
 * Called when a detection arrives that matches this track
 */
export function kalmanUpdate(
  state: KalmanState,
  measuredPosition: number,
  measuredVelocityChannelsPerMs: number,
  config: KalmanConfig,
): KalmanState {
  // Position update
  const positionInnovation = measuredPosition - state.position
  const positionKalmanGain = state.positionVariance / (state.positionVariance + config.measurementNoisePosition)

  const updatedPosition = state.position + positionKalmanGain * positionInnovation
  const updatedPositionVariance = (1 - positionKalmanGain) * state.positionVariance

  // Velocity update
  const velocityInnovation = measuredVelocityChannelsPerMs - state.velocity
  const velocityKalmanGain = state.velocityVariance / (state.velocityVariance + config.measurementNoiseVelocity)

  const updatedVelocity = state.velocity + velocityKalmanGain * velocityInnovation
  const updatedVelocityVariance = (1 - velocityKalmanGain) * state.velocityVariance

  return {
    position: updatedPosition,
    velocity: updatedVelocity,
    positionVariance: updatedPositionVariance,
    velocityVariance: updatedVelocityVariance,
  }
}

/**
 * Calculate the Mahalanobis distance for gating
 * Returns a normalized distance that accounts for uncertainty
 *
 * A value < 3 means the detection is within 3 standard deviations
 * of the predicted position (99.7% confidence interval)
 */
export function mahalanobisDistance(
  state: KalmanState,
  detectionChannel: number,
  detectionDirection: 0 | 1,
  trackDirection: 0 | 1,
): number {
  // Different directions can never match
  if (detectionDirection !== trackDirection) {
    return Infinity
  }

  const innovation = Math.abs(detectionChannel - state.position)
  const standardDeviation = Math.sqrt(state.positionVariance)

  // Normalized distance: how many standard deviations away
  return innovation / Math.max(standardDeviation, 1) // Prevent division by tiny numbers
}
