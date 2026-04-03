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

export const COLORS = {
  speed: {
    fast: '#22c55e', // green-500
    normal: '#eab308', // yellow-500
    slow: '#f97316', // orange-500
    stopped: '#ef4444', // red-500
  },
  /** RGB triples for deck.gl layers (same 4-tier scale as `speed`) */
  speedRGB: {
    fast: [34, 197, 94] as readonly [number, number, number], // green-500
    normal: [234, 179, 8] as readonly [number, number, number], // yellow-500
    slow: [249, 115, 22] as readonly [number, number, number], // orange-500
    stopped: [239, 68, 68] as readonly [number, number, number], // red-500
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
    axisStroke: 'rgba(255,255,255,0.08)', // axis/border lines on dark SVG charts
    gridLine: 'rgba(255,255,255,0.03)', // grid lines on dark SVG charts
    canvasGrid: 'rgba(148,163,184,0.1)', // canvas 2D grid lines (slate-400 at 10%)
    canvasLabel: 'rgba(148,163,184,0.4)', // canvas 2D axis labels (slate-400 at 40%)
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
    palette: [
      '#6366f1',
      '#818cf8',
      '#8b5cf6',
      '#a78bfa',
      '#0ea5e9',
      '#38bdf8',
      '#06b6d4',
      '#22d3ee',
      '#10b981',
      '#34d399',
      '#22c55e',
      '#4ade80',
      '#f59e0b',
      '#fbbf24',
      '#f97316',
      '#fb923c',
      '#ef4444',
      '#f87171',
      '#ec4899',
      '#f472b6',
      '#64748b',
      '#94a3b8',
      '#e2e8f0',
      '#ffffff',
    ] as readonly string[],
  },
  ui: {
    primary: '#3b82f6', // blue-500
    pending: '#f59e0b', // amber-500 — draw cursor for section creation
  },
  /** Mapbox layer and DOM marker colors for the dashboard map. */
  map: {
    channelDotBorder: '#ffffff',
    glowLine: '#ffffff',
    vehicleStroke: 'rgba(0,0,0,0.3)',
    pendingPointStroke: '#ffffff',
    buildingFill: '#aaaaaa',
    incidentMarkerBg: 'rgba(30,30,40,0.75)',
    incidentMarkerShadow: 'rgba(0,0,0,0.5)',
  },
} as const

// ============================================================================
// DERIVED MAPS — convenience re-exports for components that need Record<> shapes
// ============================================================================

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
