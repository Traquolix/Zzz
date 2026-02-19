export const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8001'

// Auto-detect WebSocket protocol from API URL: https -> wss, http -> ws
function deriveWsUrl(apiUrl: string): string {
    const wsProtocol = apiUrl.startsWith('https') ? 'wss' : 'ws'
    const host = apiUrl.replace(/^https?:\/\//, '')
    return `${wsProtocol}://${host}/ws/`
}

export const WS_URL = import.meta.env.VITE_WS_URL || deriveWsUrl(API_URL)