import { createContext } from 'react'

export type DataFlow = 'sim' | 'live'

export type RealtimeContextType = {
  connected: boolean
  reconnecting: boolean
  authFailed: boolean
  flow: DataFlow
  availableFlows: DataFlow[]
  setFlow: (flow: DataFlow) => void
  onFlowChange: (cb: (flow: DataFlow) => void) => () => void
  subscribe: (channel: string, callback: (data: unknown) => void) => () => void
}

export const RealtimeContext = createContext<RealtimeContextType | null>(null)
