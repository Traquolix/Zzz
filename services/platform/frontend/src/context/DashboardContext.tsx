import { createContext, useContext, useMemo, useState, useCallback, type ReactNode } from 'react'

// Widget state types
export type TrafficMonitorTab = 'landmarks' | 'sections'

type WidgetStates = {
    trafficMonitorTab: TrafficMonitorTab
}

// Display ownership - determines who renders what
type DisplayOwnership = {
    landmarkInfo: boolean  // Should map overlay show landmark info panel?
    incidentInfo: boolean  // Should map overlay show incident info panel?
    sectionInfo: boolean   // Should map overlay show section info panel?
}

type DashboardContextType = {
    // Active widgets (by base type, e.g. "traffic_monitor" not "traffic_monitor-123")
    hasWidgetType: (baseType: string) => boolean

    // Widget state registration
    widgetStates: WidgetStates
    setTrafficMonitorTab: (tab: TrafficMonitorTab) => void

    // Display ownership - computed from widget presence and state
    ownership: DisplayOwnership
}

const DashboardContext = createContext<DashboardContextType | null>(null)

type DashboardProviderProps = {
    widgetIds: string[]
    children: ReactNode
}

// Extract base widget type from ID (e.g., "traffic_monitor-123" -> "traffic_monitor")
function getBaseWidgetType(widgetId: string): string {
    const match = widgetId.match(/^([a-z_]+)/)
    return match ? match[1] : widgetId
}

export function DashboardProvider({ widgetIds, children }: DashboardProviderProps) {
    // Widget states
    const [trafficMonitorTab, setTrafficMonitorTab] = useState<TrafficMonitorTab>('landmarks')

    // Compute active widget types
    const activeWidgetTypes = useMemo(() => {
        const types = new Set<string>()
        widgetIds.forEach(id => types.add(getBaseWidgetType(id)))
        return types
    }, [widgetIds])

    const hasWidgetType = useCallback((baseType: string) => {
        return activeWidgetTypes.has(baseType)
    }, [activeWidgetTypes])

    // Compute display ownership
    const ownership = useMemo((): DisplayOwnership => {
        const hasTrafficMonitor = activeWidgetTypes.has('traffic_monitor')
        const hasIncidentsWidget = activeWidgetTypes.has('incidents')

        return {
            // Map shows landmark info if:
            // - No traffic monitor exists, OR
            // - Traffic monitor is on "sections" tab
            landmarkInfo: !hasTrafficMonitor || trafficMonitorTab === 'sections',

            // Map shows incident info if no incidents widget exists
            incidentInfo: !hasIncidentsWidget,

            // Map shows section info if:
            // - No traffic monitor exists, OR
            // - Traffic monitor is on "landmarks" tab
            sectionInfo: !hasTrafficMonitor || trafficMonitorTab === 'landmarks'
        }
    }, [activeWidgetTypes, trafficMonitorTab])

    const widgetStates = useMemo(() => ({
        trafficMonitorTab
    }), [trafficMonitorTab])

    const value = useMemo(() => ({
        hasWidgetType,
        widgetStates,
        setTrafficMonitorTab,
        ownership
    }), [hasWidgetType, widgetStates, setTrafficMonitorTab, ownership])

    return (
        <DashboardContext.Provider value={value}>
            {children}
        </DashboardContext.Provider>
    )
}

/**
 * Hook for accessing dashboard widget state and display ownership.
 * Use this for:
 * - Checking if specific widget types are present (hasWidgetType)
 * - Reading/setting widget-specific state (trafficMonitorTab)
 * - Determining display ownership (who renders landmark/incident/section info)
 *
 * Note: For widget configuration (adding/removing widgets, layouts, edit mode),
 * use the useDashboard hook from src/hooks/useDashboard.ts instead.
 */
export function useDashboardState() {
    const context = useContext(DashboardContext)
    if (!context) {
        // Fallback for components outside provider
        return {
            hasWidgetType: () => false,
            widgetStates: { trafficMonitorTab: 'landmarks' as TrafficMonitorTab },
            setTrafficMonitorTab: () => {},
            ownership: {
                landmarkInfo: true,
                incidentInfo: true,
                sectionInfo: true
            }
        }
    }
    return context
}