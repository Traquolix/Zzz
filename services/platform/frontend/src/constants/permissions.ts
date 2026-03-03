export const AVAILABLE_WIDGETS = [
    { key: 'map', labelKey: 'admin.widgetNames.map' },
    { key: 'traffic_monitor', labelKey: 'admin.widgetNames.trafficMonitor' },
    { key: 'incidents', labelKey: 'admin.widgetNames.incidents' },
    { key: 'shm', labelKey: 'admin.widgetNames.shm' },
    { key: 'admin', labelKey: 'admin.widgetNames.admin' },
] as const

export const AVAILABLE_LAYERS = [
    { key: 'cables', labelKey: 'admin.layerNames.cables' },
    { key: 'fibers', labelKey: 'admin.layerNames.fibers' },
    { key: 'vehicles', labelKey: 'admin.layerNames.vehicles' },
    { key: 'heatmap', labelKey: 'admin.layerNames.heatmap' },
    { key: 'landmarks', labelKey: 'admin.layerNames.landmarks' },
    { key: 'sections', labelKey: 'admin.layerNames.sections' },
    { key: 'detections', labelKey: 'admin.layerNames.detections' },
    { key: 'incidents', labelKey: 'admin.layerNames.incidents' },
    { key: 'infrastructure', labelKey: 'admin.layerNames.infrastructure' },
] as const
