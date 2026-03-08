/**
 * Centralized speed color utilities.
 * Provides consistent color coding for speed values across the application.
 */

export type SpeedStatus = 'fast' | 'normal' | 'slow' | 'stopped'

/**
 * Default speed thresholds (km/h).
 * Can be overridden by passing a custom normalSpeed.
 */
const DEFAULT_THRESHOLDS = {
  fast: 80,
  normal: 60,
  slow: 30,
}

/**
 * Get speed status category based on speed value.
 * @param speed - Current speed in km/h
 * @param normalSpeed - Optional reference speed for ratio-based calculation
 */
export function getSpeedStatus(speed: number, normalSpeed?: number): SpeedStatus {
  if (normalSpeed) {
    // Ratio-based calculation (used for incident context)
    const ratio = Math.min(speed / normalSpeed, 1)
    if (ratio > 0.7) return 'fast'
    if (ratio > 0.55) return 'normal'
    if (ratio > 0.4) return 'slow'
    return 'stopped'
  }

  // Absolute threshold-based calculation
  if (speed >= DEFAULT_THRESHOLDS.fast) return 'fast'
  if (speed >= DEFAULT_THRESHOLDS.normal) return 'normal'
  if (speed >= DEFAULT_THRESHOLDS.slow) return 'slow'
  return 'stopped'
}

/**
 * Get hex color for speed value.
 * @param speed - Current speed in km/h
 * @param normalSpeed - Optional reference speed for ratio-based calculation
 */
export function getSpeedHexColor(speed: number, normalSpeed?: number): string {
  const status = getSpeedStatus(speed, normalSpeed)
  switch (status) {
    case 'fast':
      return '#22c55e' // green-500
    case 'normal':
      return '#eab308' // yellow-500
    case 'slow':
      return '#f97316' // orange-500
    case 'stopped':
      return '#ef4444' // red-500
  }
}

/**
 * Get Tailwind background color class for speed indicator dots.
 * @param speed - Current speed in km/h
 * @param normalSpeed - Optional reference speed for ratio-based calculation
 */
export function getSpeedBgClass(speed: number, normalSpeed?: number): string {
  const status = getSpeedStatus(speed, normalSpeed)
  switch (status) {
    case 'fast':
      return 'bg-green-500'
    case 'normal':
      return 'bg-yellow-500'
    case 'slow':
      return 'bg-orange-500'
    case 'stopped':
      return 'bg-red-500'
  }
}

/**
 * Get Tailwind text color class for speed values.
 * @param speed - Current speed in km/h
 * @param normalSpeed - Optional reference speed for ratio-based calculation
 */
export function getSpeedTextClass(speed: number, normalSpeed?: number): string {
  const status = getSpeedStatus(speed, normalSpeed)
  switch (status) {
    case 'fast':
      return 'text-green-500'
    case 'normal':
      return 'text-yellow-500'
    case 'slow':
      return 'text-orange-500'
    case 'stopped':
      return 'text-red-500'
  }
}
