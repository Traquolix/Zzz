import { MapContainer } from "@/components/Dashboard/Widgets/Map/MapContainer"
import { useSection } from "@/hooks/useSection"
import { usePermissions } from "@/hooks/usePermissions"

// Layers - render on the map canvas (order = z-index)
import { CableLayer } from "@/components/Dashboard/Widgets/Map/layers/CableLayer"
import { FiberLayer } from "@/components/Dashboard/Widgets/Map/layers/FiberLayer"
import { SectionLayer } from "@/components/Dashboard/Widgets/Map/layers/SectionLayer"
import { SpeedHeatmapLayer } from "@/components/Dashboard/Widgets/Map/layers/SpeedHeatmapLayer"
import { VehicleLayer3D } from "@/components/Dashboard/Widgets/Map/layers/VehicleLayer3d"
import { IncidentLayer } from "@/components/Dashboard/Widgets/Map/layers/IncidentLayer"
import { LandmarkSelectionLayer } from "@/components/Dashboard/Widgets/Map/layers/LandmarkSelectionLayer"
import { InfrastructureLayer } from "@/components/Dashboard/Widgets/Map/layers/InfrastructureLayer"
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

export function Map() {
    const { layerVisibility } = useSection()
    const { hasLayer } = usePermissions()

    return (
        <MapContainer>
            {/* Layers - render order matters for z-index. Both permission AND visibility must be true. */}
            {hasLayer('cables') && layerVisibility.cables && <CableLayer />}
            {hasLayer('fibers') && layerVisibility.fibers && <FiberLayer />}
            {hasLayer('sections') && layerVisibility.sections && <SectionLayer />}
            {hasLayer('heatmap') && layerVisibility.heatmap && <SpeedHeatmapLayer />}
            {hasLayer('vehicles') && layerVisibility.vehicles && <VehicleLayer3D />}
            {hasLayer('incidents') && layerVisibility.incidents && <IncidentLayer />}
            {hasLayer('infrastructure') && layerVisibility.infrastructure && <InfrastructureLayer />}
            {hasLayer('landmarks') && <LandmarkSelectionLayer />}
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
    )
}
