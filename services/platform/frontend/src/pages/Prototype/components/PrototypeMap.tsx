import { useRef, useMemo, forwardRef, useImperativeHandle, memo } from 'react'
import { findFiber } from '../data'
import type { Fiber, Section, PendingPoint, LiveSectionStats, SpeedThresholds, ProtoIncident } from '../types'
import type { Infrastructure } from '@/types/infrastructure'
import type { VehiclePosition } from '../hooks/useVehicleSim'
import { useMapInstance } from './hooks/useMapInstance'
import { useMapLayers } from './hooks/useMapLayers'
import { useMapHighlights } from './hooks/useMapHighlights'
import { useIncidentMarkers } from './hooks/useIncidentMarkers'
import { useStructureMarkers } from './hooks/useStructureMarkers'
import { useVehiclePopup } from './hooks/useVehiclePopup'
import { useRenderLoop } from './hooks/useRenderLoop'
import { useMapInteractions } from './hooks/useMapInteractions'
import { useMapToggles } from './hooks/useMapToggles'

export interface PrototypeMapHandle {
  flyTo: (center: [number, number], zoom?: number) => void
  highlightFiber: (fiberId: string) => void
  highlightSection: (sectionId: string) => void
  highlightIncident: (incidentId: string) => void
  highlightStructure: (structureId: string, structures: Infrastructure[]) => void
  highlightChannel: (lng: number, lat: number) => void
  clearHighlight: () => void
}

interface PrototypeMapProps {
  incidents?: ProtoIncident[]
  onIncidentClick?: (id: string) => void
  onMapClick?: () => void
  sectionCreationMode?: boolean
  pendingPoint?: PendingPoint | null
  sections?: Section[]
  selectedSectionId?: string | null
  onFiberClick?: (point: PendingPoint) => void
  onSectionComplete?: (fiberId: string, direction: 0 | 1, startChannel: number, endChannel: number) => void
  buildVehicleGeoJSON?: () => GeoJSON.FeatureCollection
  tickAndCollect?: (now: number, deltaMs: number) => VehiclePosition[]
  displayMode?: 'dots' | 'vehicles'
  liveStats?: Map<string, LiveSectionStats>
  onOverviewChange?: (isOverview: boolean) => void
  thresholdLookup?: (cableId: string, direction: 0 | 1, channel: number) => SpeedThresholds
  fiberColors?: Record<string, string>
  structures?: Infrastructure[]
  structureStatuses?: Map<string, import('@/types/infrastructure').SHMStatus>
  showStructuresOnMap?: boolean
  showStructureLabels?: boolean
  selectedStructureId?: string | null
  onStructureClick?: (id: string) => void
  onChannelClick?: (point: PendingPoint) => void
  sidebarOpen?: boolean
  hideFibersInOverview?: boolean
  show3DBuildings?: boolean
  showChannelHelper?: boolean
}

export const PrototypeMap = memo(
  forwardRef<PrototypeMapHandle, PrototypeMapProps>(function PrototypeMap(
    {
      incidents,
      onIncidentClick,
      onMapClick,
      sectionCreationMode,
      pendingPoint,
      sections,
      onFiberClick,
      onSectionComplete,
      buildVehicleGeoJSON,
      tickAndCollect,
      displayMode = 'dots',
      liveStats,
      onOverviewChange,
      thresholdLookup,
      fiberColors,
      structures,
      structureStatuses,
      showStructuresOnMap,
      showStructureLabels,
      selectedStructureId,
      onStructureClick,
      onChannelClick,
      sidebarOpen,
      hideFibersInOverview,
      show3DBuildings,
      showChannelHelper,
    },
    ref,
  ) {
    // ── Closure-capture refs (bridge props → stable refs for effects) ──
    const incidentClickedRef = useRef(false)
    const handlersRef = useRef({
      onIncidentClick,
      onMapClick,
      onFiberClick,
      onSectionComplete,
      onOverviewChange,
      onChannelClick,
    })
    handlersRef.current = {
      onIncidentClick,
      onMapClick,
      onFiberClick,
      onSectionComplete,
      onOverviewChange,
      onChannelClick,
    }

    const pendingPointRef = useRef(pendingPoint)
    pendingPointRef.current = pendingPoint

    const sectionCreationRef = useRef(sectionCreationMode)
    sectionCreationRef.current = sectionCreationMode

    const buildGeoJSONRef = useRef(buildVehicleGeoJSON)
    buildGeoJSONRef.current = buildVehicleGeoJSON

    const tickAndCollectRef = useRef(tickAndCollect)
    tickAndCollectRef.current = tickAndCollect

    const displayModeRef = useRef(displayMode)
    displayModeRef.current = displayMode

    const liveStatsRef = useRef(liveStats)
    liveStatsRef.current = liveStats

    const sectionsRef = useRef(sections)
    sectionsRef.current = sections

    const sectionFibersRef = useRef(new Map<string, Fiber>())
    const sectionFibers = useMemo(() => {
      const m = new Map<string, Fiber>()
      for (const sec of sections ?? []) {
        const f = findFiber(sec.fiberId, sec.direction)
        if (f) m.set(sec.id, f)
      }
      return m
    }, [sections])
    sectionFibersRef.current = sectionFibers

    const thresholdLookupRef = useRef(thresholdLookup)
    thresholdLookupRef.current = thresholdLookup

    const fiberColorsRef = useRef(fiberColors)
    fiberColorsRef.current = fiberColors

    const sidebarOpenRef = useRef(sidebarOpen)
    sidebarOpenRef.current = sidebarOpen

    const overviewRef = useRef(false)
    const hideFibersRef = useRef(hideFibersInOverview)
    hideFibersRef.current = hideFibersInOverview

    const onStructureClickRef = useRef(onStructureClick)
    onStructureClickRef.current = onStructureClick

    // ── Hooks (order matters: layers must register before render loop) ──
    const { containerRef, mapRef } = useMapInstance()
    useMapLayers(mapRef)

    const { markersRef } = useIncidentMarkers({
      mapRef,
      incidents,
      incidentClickedRef,
      handlersRef,
    })

    useStructureMarkers({
      mapRef,
      structures,
      structureStatuses,
      showStructuresOnMap,
      showStructureLabels,
      selectedStructureId,
      onStructureClickRef,
    })

    const highlights = useMapHighlights({
      mapRef,
      markersRef,
      sectionsRef,
      fiberColorsRef,
      sidebarOpenRef,
    })

    const vehiclePopup = useVehiclePopup({ mapRef, thresholdLookupRef })

    const { vehicleClickedRef, deckOverlayRef } = useRenderLoop({
      mapRef,
      overviewRef,
      displayModeRef,
      buildGeoJSONRef,
      tickAndCollectRef,
      liveStatsRef,
      sectionsRef,
      sectionFibersRef,
      thresholdLookupRef,
      vehiclePopup,
    })

    useMapInteractions({
      mapRef,
      handlersRef,
      pendingPointRef,
      sectionCreationRef,
      incidentClickedRef,
      vehicleClickedRef,
      overviewRef,
      hideFibersRef,
      deckOverlayRef,
      dismissVehiclePopup: vehiclePopup.dismiss,
    })

    useMapToggles({
      mapRef,
      sections,
      fiberColors,
      pendingPoint,
      hideFibersInOverview,
      show3DBuildings,
      showChannelHelper,
      sectionCreationMode,
      sectionFibersRef,
      fiberColorsRef,
      overviewRef,
    })

    useImperativeHandle(ref, () => highlights)

    return (
      <div className="relative w-full h-full">
        <div ref={containerRef} className="w-full h-full" />
      </div>
    )
  }),
)
