import { create } from 'zustand'
import type { DataFlow } from '@/context/RealtimeContext'

/**
 * Global application store — Zustand.
 *
 * Houses cross-cutting state that many components need with fine-grained
 * subscriptions. Each component subscribes via selector:
 *
 *   const connected = useAppStore(s => s.connected)
 *
 * Only re-renders when the selected value changes (referential equality).
 *
 * Slices:
 * - Connection: WebSocket status, pushed by RealtimeProvider
 * - Flow: current data flow (sim/live)
 */

type AppState = {
  // --- Connection slice ---
  connected: boolean
  authFailed: boolean
  setConnected: (connected: boolean) => void
  setAuthFailed: (failed: boolean) => void
  // --- Flow slice ---
  flow: DataFlow
  setFlow: (flow: DataFlow) => void
}

export const useAppStore = create<AppState>()(set => ({
  // Connection
  connected: false,
  authFailed: false,
  setConnected: connected =>
    set({
      connected,
      // Successful connection clears auth failure
      ...(connected ? { authFailed: false } : {}),
    }),
  setAuthFailed: authFailed => set({ authFailed }),
  // Flow
  flow: 'sim' as DataFlow,
  setFlow: flow => set({ flow }),
}))
