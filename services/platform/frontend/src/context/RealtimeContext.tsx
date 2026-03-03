import { createContext } from 'react'

export type RealtimeContextType = {
    connected: boolean
    reconnecting: boolean
    authFailed: boolean
    subscribe: (channel: string, callback: (data: unknown) => void) => () => void
}

export const RealtimeContext = createContext<RealtimeContextType | null>(null)