// Use VITE_API_URL if set, otherwise default to localhost for dev
// Empty string means same-origin (for reverse proxy setups)
const envUrl = import.meta.env.VITE_API_URL
export const API_URL = envUrl !== undefined ? envUrl : 'http://localhost:8001'

// Auto-detect WebSocket protocol from API URL: https -> wss, http -> ws
function deriveWsUrl(apiUrl: string): string {
    const wsProtocol = apiUrl.startsWith('https') ? 'wss' : 'ws'
    const host = apiUrl.replace(/^https?:\/\//, '')
    return `${wsProtocol}://${host}/ws/`
}

export const WS_URL = import.meta.env.VITE_WS_URL || deriveWsUrl(API_URL)