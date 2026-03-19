/**
 * Centralized design tokens — single source of truth for all visual constants.
 *
 * Every color, spacing value, shadow, z-index, and typography class used
 * across the application should reference this file. Canvas-based components
 * use the HEX values; Tailwind-based components use the class maps.
 *
 * If you add a new color or change an existing one, change it HERE.
 */

// ============================================================================
// COLORS — Hex values for canvas/mapbox/deck.gl, Tailwind classes for UI
// ============================================================================

/**
 * Severity colors — used for incidents across all components.
 * Re-exported from constants/incidents.ts for backwards compatibility,
 * but this is the canonical reference.
 */
export const COLORS = {
  /** Incident severity — matches the live values used by all 17+ Prototype components. */
  severity: {
    critical: '#ef4444', // red-500
    high: '#f97316', // orange-500
    medium: '#f59e0b', // amber-500
    low: '#22c55e', // green-500
  },
  speed: {
    fast: '#22c55e', // green-500
    normal: '#eab308', // yellow-500
    slow: '#f97316', // orange-500
    stopped: '#ef4444', // red-500
  },
  /** Chart metric colors — speed, flow, occupancy line/sparkline colors. */
  chart: {
    speed: '#6366f1', // indigo-500
    flow: '#8b5cf6', // purple-500
    occupancy: '#0ea5e9', // sky-500
  },
  /** Infrastructure structure-type colors (SHM panels, map markers). */
  structure: {
    bridge: { bg: '#f59e0b', text: '#fbbf24', dot: '#f59e0b' },
    tunnel: { bg: '#6366f1', text: '#818cf8', dot: '#6366f1' },
  },
  /** SHM health status colors. */
  shmStatus: {
    nominal: '#22c55e', // green-500
    warning: '#f59e0b', // amber-500
    critical: '#ef4444', // red-500
  },
  /** Waterfall canvas background/grid/label colors (dark theme). */
  waterfall: {
    background: '#0f172a', // slate-900
    grid: '#1e293b', // slate-800
    label: '#64748b', // slate-500
  },
  /** SHM chart axis/tick colors. */
  shmChart: {
    axis: '#64748b', // slate-500 — tick marks, axis labels
    axisSecondary: '#4a5568', // gray-600 — comparison chart text
    scatter: '#f59e0b', // amber-500 — peak scatter dots
    comparisonA: '#3b82f6', // blue-500
    comparisonB: '#f59e0b', // amber-500
  },
  /** Time-series chart (Recharts) colors. */
  timeSeries: {
    tickFill: '#64748b', // slate-500
    tooltipBg: '#2b2d31',
    tooltipBorder: 'rgba(255,255,255,0.08)',
    tooltipText: '#e2e8f0', // slate-200
  },
  /** Default fiber color when no user override is set. */
  fiber: {
    default: '#94a3b8', // slate-400
  },
  ui: {
    primary: '#3b82f6', // blue-500
    primaryHover: '#2563eb', // blue-600
    border: '#e2e8f0', // slate-200
    borderHover: '#cbd5e1', // slate-300
    text: '#1e293b', // slate-800
    textSecondary: '#64748b', // slate-500
    textMuted: '#94a3b8', // slate-400
    background: '#ffffff',
    backgroundMuted: '#f8fafc', // slate-50
    danger: '#dc2626', // red-600
    success: '#16a34a', // green-600
  },
  /**
   * 5-tier speed gradient — used for speed-limit-relative coloring
   * on maps and deck.gl layers. Finer granularity than `speed` (4-tier).
   */
  speedGradient: {
    flowing: '#22c55e', // green-500  — ≥80% of limit
    moderate: '#84cc16', // lime-500   — ≥60% of limit
    slowing: '#eab308', // yellow-500 — ≥40% of limit
    congested: '#f97316', // orange-500 — ≥20% of limit
    severe: '#ef4444', // red-500    — <20% of limit
  },
  /** RGB triples for deck.gl layers (same order as speedGradient) */
  speedGradientRGB: {
    flowing: [34, 197, 94] as readonly [number, number, number],
    moderate: [132, 204, 22] as readonly [number, number, number],
    slowing: [234, 179, 8] as readonly [number, number, number],
    congested: [249, 115, 22] as readonly [number, number, number],
    severe: [239, 68, 68] as readonly [number, number, number],
  },
  /** Speed-limit zone category colors (classifying the limit value itself) */
  limitZone: {
    highway: '#3b82f6', // blue-500  — ≥100 km/h
    fastRoad: '#8b5cf6', // purple-500 — ≥70 km/h
    urban: '#f59e0b', // amber-500 — ≥50 km/h
    slowZone: '#ef4444', // red-500   — <50 km/h
  },
  /** Canvas/chart axis and grid colors (light theme) */
  canvas: {
    axis: '#64748b', // slate-500
    grid: '#e2e8f0', // slate-200
    label: '#94a3b8', // slate-400
    background: '#ffffff',
  },
} as const

// ============================================================================
// DERIVED MAPS — convenience re-exports for components that need Record<> shapes
// ============================================================================

export const severityColor: Record<string, string> = {
  critical: COLORS.severity.critical,
  high: COLORS.severity.high,
  medium: COLORS.severity.medium,
  low: COLORS.severity.low,
}

export const chartColors = {
  speed: { label: 'Speed', unit: 'km/h', color: COLORS.chart.speed },
  flow: { label: 'Flow', unit: 'veh/h', color: COLORS.chart.flow },
  occupancy: { label: 'Occupancy', unit: '%', color: COLORS.chart.occupancy },
}

export const structureTypeColors: Record<string, { bg: string; text: string; dot: string }> = {
  bridge: COLORS.structure.bridge,
  tunnel: COLORS.structure.tunnel,
}

export const shmStatusColors: Record<string, string> = {
  nominal: COLORS.shmStatus.nominal,
  warning: COLORS.shmStatus.warning,
  critical: COLORS.shmStatus.critical,
}

// ============================================================================
// CANVAS HELPERS — For SpectralHeatmap, SnapshotChart, and similar
// ============================================================================

/**
 * Get speed hex color for canvas drawing.
 */
export function getSpeedHex(status: 'fast' | 'normal' | 'slow' | 'stopped'): string {
  return COLORS.speed[status]
}

/**
 * 5-tier speed gradient: hex color based on percentage of speed limit.
 * Falls back to absolute thresholds when no limit is provided.
 */
export function speedToColorWithLimit(speed: number, limit: number | null): string {
  if (limit && limit > 0) {
    const pct = speed / limit
    if (pct >= 0.8) return COLORS.speedGradient.flowing
    if (pct >= 0.6) return COLORS.speedGradient.moderate
    if (pct >= 0.4) return COLORS.speedGradient.slowing
    if (pct >= 0.2) return COLORS.speedGradient.congested
    return COLORS.speedGradient.severe
  }
  if (speed >= 80) return COLORS.speedGradient.flowing
  if (speed >= 60) return COLORS.speedGradient.moderate
  if (speed >= 40) return COLORS.speedGradient.slowing
  if (speed >= 20) return COLORS.speedGradient.congested
  return COLORS.speedGradient.severe
}

/**
 * 5-tier speed gradient: RGB triple for deck.gl layers.
 * Falls back to absolute thresholds when no limit is provided.
 */
export function speedToRGBWithLimit(speed: number, limit: number | null): [number, number, number] {
  if (limit && limit > 0) {
    const pct = speed / limit
    if (pct >= 0.8) return [...COLORS.speedGradientRGB.flowing]
    if (pct >= 0.6) return [...COLORS.speedGradientRGB.moderate]
    if (pct >= 0.4) return [...COLORS.speedGradientRGB.slowing]
    if (pct >= 0.2) return [...COLORS.speedGradientRGB.congested]
    return [...COLORS.speedGradientRGB.severe]
  }
  if (speed >= 80) return [...COLORS.speedGradientRGB.flowing]
  if (speed >= 60) return [...COLORS.speedGradientRGB.moderate]
  if (speed >= 40) return [...COLORS.speedGradientRGB.slowing]
  if (speed >= 20) return [...COLORS.speedGradientRGB.congested]
  return [...COLORS.speedGradientRGB.severe]
}

/**
 * Get color for a speed-limit zone category.
 */
export function getLimitZoneColor(limit: number): string {
  if (limit >= 100) return COLORS.limitZone.highway
  if (limit >= 70) return COLORS.limitZone.fastRoad
  if (limit >= 50) return COLORS.limitZone.urban
  return COLORS.limitZone.slowZone
}
