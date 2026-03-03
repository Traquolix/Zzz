/**
 * Context for TrafficMonitor callback handlers.
 *
 * Eliminates prop drilling of 5 callback functions through TrafficMonitorWidget
 * → LandmarkList → individual landmark items. Data props (landmarks, fibers,
 * landmarkData, selectedKey, now) stay as regular props since they change frequently
 * and benefit from React's normal diffing.
 */

import { createContext, useContext, type ReactNode } from 'react'
import type { LandmarkInfo } from './types'

export type TrafficMonitorActions = {
    onSelect: (landmark: LandmarkInfo) => void
    onFlyTo: (landmark: LandmarkInfo, e: React.MouseEvent) => void
    onRename: (fiberId: string, channel: number, name: string) => void
    onToggleFavorite: (fiberId: string, channel: number) => void
    onDelete: (fiberId: string, channel: number) => void
}

const TrafficMonitorActionsContext = createContext<TrafficMonitorActions | null>(null)

export function TrafficMonitorActionsProvider({
    actions,
    children,
}: {
    actions: TrafficMonitorActions
    children: ReactNode
}) {
    return (
        <TrafficMonitorActionsContext.Provider value={actions}>
            {children}
        </TrafficMonitorActionsContext.Provider>
    )
}

export function useTrafficMonitorActions(): TrafficMonitorActions {
    const ctx = useContext(TrafficMonitorActionsContext)
    if (!ctx) {
        throw new Error('useTrafficMonitorActions must be used within TrafficMonitorActionsProvider')
    }
    return ctx
}
