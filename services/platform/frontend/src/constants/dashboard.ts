import { Map } from '@/components/Dashboard/Widgets/Map/Map'
import { TrafficMonitorWidget } from '@/components/Dashboard/Widgets/TrafficMonitor'
import { IncidentWidget } from '@/components/Dashboard/Widgets/IncidentWidget'
import { SHMWidget } from '@/components/Dashboard/Widgets/SHMWidget'
import type { ComponentType } from 'react'
import type { Layouts } from "@/types/dashboard"
import type { LucideIcon } from 'lucide-react'
import { MapIcon, Activity, AlertTriangle, Building2 } from 'lucide-react'

export const WIDGET_REGISTRY: Record<string, { component: ComponentType; name: string; icon: LucideIcon; defaultSize: { w: number; h: number } }> = {
    map: { component: Map, name: 'Map', icon: MapIcon, defaultSize: { w: 30, h: 20 } },
    traffic_monitor: { component: TrafficMonitorWidget, name: 'Traffic Monitor', icon: Activity, defaultSize: { w: 4, h: 6 } },
    incidents: { component: IncidentWidget, name: 'Incidents', icon: AlertTriangle, defaultSize: { w: 3, h: 3 } },
    shm: { component: SHMWidget, name: 'Structural Health', icon: Building2, defaultSize: { w: 4, h: 6 } },
}

export const DEFAULT_LAYOUTS: Layouts = {
    lg: [
        { i: 'map', x: 0, y: 0, w: 5, h: 11 },
        { i: 'traffic_monitor', x: 5, y: 0, w: 4, h: 7 },
        { i: 'incidents', x: 9, y: 0, w: 3, h: 11 },
    ],
    md: [
        { i: 'map', x: 0, y: 0, w: 4, h: 11 },
        { i: 'traffic_monitor', x: 4, y: 0, w: 3, h: 7 },
        { i: 'incidents', x: 7, y: 0, w: 3, h: 11 },
    ],
    sm: [
        { i: 'map', x: 0, y: 0, w: 6, h: 6 },
        { i: 'traffic_monitor', x: 0, y: 6, w: 3, h: 3 },
        { i: 'incidents', x: 3, y: 6, w: 3, h: 6 },
    ],
    xs: [
        { i: 'map', x: 0, y: 0, w: 4, h: 6 },
        { i: 'traffic_monitor', x: 0, y: 6, w: 4, h: 3 },
        { i: 'incidents', x: 0, y: 9, w: 4, h: 6 },
    ],
}

export const BREAKPOINTS = { lg: 1200, md: 996, sm: 768, xs: 480 }
export const COLS = { lg: 12, md: 10, sm: 6, xs: 4 }

export const DEFAULT_WIDGETS = [
    { id: 'map', name: 'Map', component: Map },
    { id: 'traffic_monitor', name: 'Traffic Monitor', component: TrafficMonitorWidget },
    { id: 'incidents', name: 'Incidents', component: IncidentWidget },
    { id: 'shm', name: 'Structural Health', component: SHMWidget },
]