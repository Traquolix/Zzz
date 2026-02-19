/**
 * Shared incident severity constants — single source of truth.
 *
 * Hex colors are used by map layers (deck.gl, mapbox).
 * Tailwind variants are used by UI components.
 */

export const SEVERITY_HEX: Record<string, string> = {
    low: '#eab308',
    medium: '#f97316',
    high: '#ef4444',
    critical: '#dc2626',
}

export const SEVERITY_BADGE: Record<string, { bg: string; text: string; border: string }> = {
    low: { bg: 'bg-yellow-50', text: 'text-yellow-700', border: 'border-yellow-200' },
    medium: { bg: 'bg-orange-50', text: 'text-orange-700', border: 'border-orange-200' },
    high: { bg: 'bg-red-50', text: 'text-red-700', border: 'border-red-200' },
    critical: { bg: 'bg-red-100', text: 'text-red-800', border: 'border-red-300' },
}

export const SEVERITY_INDICATOR: Record<string, { color: string; pulse: boolean }> = {
    critical: { color: 'bg-red-500', pulse: true },
    high: { color: 'bg-red-400', pulse: false },
    medium: { color: 'bg-orange-400', pulse: false },
    low: { color: 'bg-yellow-400', pulse: false },
}

export const SEVERITY_DETAIL: Record<string, string> = {
    critical: 'text-red-600 bg-red-50',
    high: 'text-orange-600 bg-orange-50',
    medium: 'text-yellow-600 bg-yellow-50',
    low: 'text-blue-600 bg-blue-50',
}

export const SEVERITY_DOT: Record<string, string> = {
    critical: 'bg-red-500 border-red-600',
    high: 'bg-orange-500 border-orange-600',
    medium: 'bg-yellow-500 border-yellow-600',
    low: 'bg-blue-500 border-blue-600',
}

export const SEVERITY_TEXT: Record<string, string> = {
    critical: 'text-red-600',
    high: 'text-orange-600',
    medium: 'text-yellow-600',
    low: 'text-blue-600',
}

export const INCIDENT_TYPE_LABELS: Record<string, string> = {
    slowdown: 'Slowdown',
    congestion: 'Congestion',
    accident: 'Accident',
    anomaly: 'Anomaly',
}
