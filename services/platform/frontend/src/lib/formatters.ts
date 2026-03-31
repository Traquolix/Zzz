/**
 * Shared formatting utilities — single source of truth for all
 * duration, date, and time formatting across the application.
 *
 * All date/time formatting uses a configurable IANA timezone
 * (default: Europe/Paris) to ensure French highway operators
 * see local time, not UTC.
 */

const SECONDS_PER_MINUTE = 60
const SECONDS_PER_HOUR = 3600
const SECONDS_PER_DAY = 86400

const _timezone = 'Europe/Paris'

type DateInput = string | number | Date

/** Normalize any date input to a Date object. */
function toDate(input: DateInput): Date {
  return input instanceof Date ? input : new Date(input)
}

// --- Duration formatting (timezone-independent) ---

/**
 * Format a duration in seconds to a human-readable string.
 *
 * Examples:
 *   45.3   -> "45.3s"
 *   125    -> "2m 5s"
 *   3700   -> "1h 1m"
 *   90000  -> "1d 1h"
 */
export function formatDuration(seconds: number): string {
  if (seconds < SECONDS_PER_MINUTE) {
    return `${seconds.toFixed(1)}s`
  }
  if (seconds < SECONDS_PER_HOUR) {
    const mins = Math.floor(seconds / SECONDS_PER_MINUTE)
    const secs = Math.round(seconds % SECONDS_PER_MINUTE)
    return `${mins}m ${secs}s`
  }
  if (seconds < SECONDS_PER_DAY) {
    const hrs = Math.floor(seconds / SECONDS_PER_HOUR)
    const mins = Math.round((seconds % SECONDS_PER_HOUR) / SECONDS_PER_MINUTE)
    if (mins === 60) return `${hrs + 1}h 0m`
    return `${hrs}h ${mins}m`
  }
  const days = Math.floor(seconds / SECONDS_PER_DAY)
  const hrs = Math.round((seconds % SECONDS_PER_DAY) / SECONDS_PER_HOUR)
  if (hrs === 24) return `${days + 1}d 0h`
  return `${days}d ${hrs}h`
}

/**
 * Format a duration in milliseconds.
 */
export function formatDurationMs(ms: number): string {
  return formatDuration(ms / 1000)
}

// --- Timezone-aware date/time formatting ---

/**
 * Format a timestamp to time string (HH:MM:SS) in configured timezone.
 */
export function formatTime(input: DateInput): string {
  const date = toDate(input)
  if (isNaN(date.getTime())) return '--:--:--'
  return date.toLocaleTimeString('en-GB', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    timeZone: _timezone,
  })
}

/**
 * Format a timestamp to short time string (HH:MM) in configured timezone.
 */
export function formatTimeShort(input: DateInput): string {
  const date = toDate(input)
  if (isNaN(date.getTime())) return '--:--'
  return date.toLocaleTimeString('en-GB', {
    hour: '2-digit',
    minute: '2-digit',
    timeZone: _timezone,
  })
}

/**
 * Format a timestamp to date string (locale-appropriate) in configured timezone.
 */
export function formatDate(input: DateInput): string {
  const date = toDate(input)
  if (isNaN(date.getTime())) return '---'
  return date.toLocaleDateString(undefined, {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
    timeZone: _timezone,
  })
}

/**
 * Format a timestamp to short date string (e.g. "Mar 31") in configured timezone.
 */
export function formatDateShort(input: DateInput): string {
  const date = toDate(input)
  if (isNaN(date.getTime())) return '---'
  return date.toLocaleDateString(undefined, {
    day: 'numeric',
    month: 'short',
    timeZone: _timezone,
  })
}

/**
 * Format a timestamp to combined date + time string in configured timezone.
 */
export function formatDateTime(input: DateInput): string {
  const date = toDate(input)
  if (isNaN(date.getTime())) return '---'
  const datePart = date.toLocaleDateString(undefined, {
    day: 'numeric',
    month: 'short',
    timeZone: _timezone,
  })
  const timePart = date.toLocaleTimeString('en-GB', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    timeZone: _timezone,
  })
  return `${datePart} ${timePart}`
}

/**
 * Format a timestamp to hour-only label (e.g. "14:00") in configured timezone.
 * Useful for chart axis labels.
 */
export function formatHour(input: DateInput): string {
  const date = toDate(input)
  if (isNaN(date.getTime())) return '--:--'
  return date.toLocaleTimeString('en-GB', {
    hour: '2-digit',
    minute: '2-digit',
    timeZone: _timezone,
  })
}
