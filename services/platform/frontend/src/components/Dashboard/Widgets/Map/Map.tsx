import { MapContainer } from "@/components/Dashboard/Widgets/Map/MapContainer"
import { useSection } from "@/hooks/useSection"
import { usePermissions } from "@/hooks/usePermissions"
import { ErrorBoundary } from "@/components/ui/ErrorBoundary"
import { useTranslation } from "react-i18next"

// Layers - render on the map canvas (order = z-index)
import { CableLayer } from "@/components/Dashboard/Widgets/Map/layers/CableLayer"
import { FiberLayer } from "@/components/Dashboard/Widgets/Map/layers/FiberLayer"
import { SectionLayer } from "@/components/Dashboard/Widgets/Map/layers/SectionLayer"
import { SpeedHeatmapLayer } from "@/components/Dashboard/Widgets/Map/layers/SpeedHeatmapLayer"
import { VehicleLayer3D } from "@/components/Dashboard/Widgets/Map/layers/VehicleLayer3d"
import { IncidentLayer } from "@/components/Dashboard/Widgets/Map/layers/IncidentLayer"
import { LandmarkSelectionLayer } from "@/components/Dashboard/Widgets/Map/layers/LandmarkSelectionLayer"
import { InfrastructureLayer } from "@/components/Dashboard/Widgets/Map/layers/InfrastructureLayer"
import { ChannelDotLayer } from "@/components/Dashboard/Widgets/Map/layers/ChannelDotLayer"
import { ClickHandler } from "@/components/Dashboard/Widgets/Map/layers/ClickHandler"

// Info panels - floating UI for selected items
import { LandmarkInfoPanel } from "@/components/Dashboard/Widgets/Map/overlays/LandmarkInfoPanel"
import { VehicleInfoPanel } from "@/components/Dashboard/Widgets/Map/overlays/VehicleInfoPanel"
import { SectionInfoPanel } from "@/components/Dashboard/Widgets/Map/overlays/SectionInfoPanel"
import { IncidentInfoPanel } from "@/components/Dashboard/Widgets/Map/overlays/IncidentInfoPanel"

// Section editing UI
import { SectionResizeHandles } from "@/components/Dashboard/Widgets/Map/overlays/SectionResizeHandles"
import { SectionNamingDialog } from "@/components/Dashboard/Widgets/Map/overlays/SectionNamingDialog"
import { SectionCreationIndicator } from "@/components/Dashboard/Widgets/Map/overlays/SectionCreationIndicator"

// Controls
import { MapControls } from "@/components/Dashboard/Widgets/Map/overlays/MapControls"

function MapFallback() {
    const { t } = useTranslation()
    return (
        <div className="flex flex-col items-center justify-center h-full bg-slate-100 rounded-lg">
            <div className="text-slate-400 mb-2">
                <svg className="w-12 h-12" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l4.553 2.276A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 4m0 13V4m0 0L9 7" />
                </svg>
            </div>
            <p className="text-sm text-slate-500">{t('map.renderError', 'Map failed to render')}</p>
            <p className="text-xs text-slate-400 mt-1">{t('map.renderErrorHint', 'Try reloading the page')}</p>
        </div>
    )
}

export function Map() {
    const { layerVisibility } = useSection()
    const { hasLayer } = usePermissions()

    return (
        <ErrorBoundary fallback={<MapFallback />}>
        <MapContainer>
            {/* Layers - render order matters for z-index. Both permission AND visibility must be true. */}
            {hasLayer('cables') && layerVisibility.cables && <CableLayer />}
            {hasLayer('fibers') && layerVisibility.fibers && <FiberLayer />}
            {hasLayer('sections') && layerVisibility.sections && <SectionLayer />}
            {hasLayer('heatmap') && layerVisibility.heatmap && <SpeedHeatmapLayer />}
            {hasLayer('detections') && layerVisibility.detections && <ChannelDotLayer />}
            {hasLayer('vehicles') && layerVisibility.vehicles && <VehicleLayer3D />}
            {hasLayer('incidents') && layerVisibility.incidents && (
                <ErrorBoundary fallback={<div className="text-xs text-red-500 p-2">Incident layer failed to load</div>}>
                    <IncidentLayer />
                </ErrorBoundary>
            )}
            {hasLayer('infrastructure') && layerVisibility.infrastructure && <InfrastructureLayer />}
            {hasLayer('landmarks') && layerVisibility.landmarks && <LandmarkSelectionLayer />}
            <ClickHandler />

            {/* Info panels - permission-gated */}
            {hasLayer('landmarks') && <LandmarkInfoPanel />}
            {hasLayer('vehicles') && <VehicleInfoPanel />}
            {hasLayer('sections') && <SectionInfoPanel />}
            {hasLayer('incidents') && <IncidentInfoPanel />}

            {/* Section editing - only if user has sections permission */}
            {hasLayer('sections') && <SectionResizeHandles />}
            {hasLayer('sections') && <SectionNamingDialog />}
            {hasLayer('sections') && <SectionCreationIndicator />}

            {/* Controls */}
            <MapControls />
        </MapContainer>
        </ErrorBoundary>
    )
}
