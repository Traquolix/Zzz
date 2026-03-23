import { useEffect, useRef, useCallback, useMemo, useContext, forwardRef, useImperativeHandle, memo } from 'react'
import mapboxgl from 'mapbox-gl'
import 'mapbox-gl/dist/mapbox-gl.css'
import { MapboxOverlay } from '@deck.gl/mapbox'
import { SimpleMeshLayer } from '@deck.gl/mesh-layers'
import { CubeGeometry } from '@luma.gl/engine'
import { MAPBOX_TOKEN } from '@/config/mapbox'
import { COLORS, shmStatusColors as shmStatusColorsMap } from '@/lib/theme'
import {
  fibers,
  fiberOffsetCache,
  fiberRenderCache,
  severityColor,
  MAP_CENTER,
  MAP_ZOOM,
  getSpeedColor,
  getSectionCoords,
  getSpeedColorRGBA,
  findFiber,
  getFiberColor,
  channelToCoord,
} from '../data'
import type { Fiber, Section, PendingPoint, LiveSectionStats, SpeedThresholds, ProtoIncident } from '../types'
import type { Infrastructure } from '@/types/infrastructure'
import type { VehiclePosition } from '../hooks/useVehicleSim'
import { getSidebarWidth, SidebarRefContext } from '../hooks/useSidebarWidth'
import i18n from '@/i18n'
import {
  findNearestFiberPoint,
  getPosition,
  getOrientation,
  getScale,
  FIBER_WIDTH_EXPR,
  FIBER_OPACITY_EXPR,
  buildSectionHighlightData,
} from './mapUtils'

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
    const sidebarRef = useContext(SidebarRefContext)
    const containerRef = useRef<HTMLDivElement>(null)
    const mapRef = useRef<mapboxgl.Map | null>(null)
    const markersRef = useRef<Map<string, mapboxgl.Marker>>(new Map())
    const incidentClickedRef = useRef(false)
    const vehicleClickedRef = useRef(false)
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

    // Pre-resolve fibers for sections once (avoids per-section findFiber in hot loops)
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

    const deckOverlayRef = useRef<MapboxOverlay | null>(null)
    const cubeRef = useRef<CubeGeometry | null>(null)

    const highlightTimerRef = useRef<number | null>(null)
    const highlightedMarkerRef = useRef<HTMLElement | null>(null)
    const channelMarkerRef = useRef<mapboxgl.Marker | null>(null)
    const structureMarkersRef = useRef<Map<string, mapboxgl.Marker>>(new Map())
    const onStructureClickRef = useRef(onStructureClick)
    onStructureClickRef.current = onStructureClick

    const clearHighlightImpl = useCallback(() => {
      const map = mapRef.current
      if (!map) return
      // Stop pulse timer
      if (highlightTimerRef.current != null) {
        clearInterval(highlightTimerRef.current)
        highlightTimerRef.current = null
      }
      // Restore fiber layer to default zoom-driven expressions
      if (map.getLayer('fiber-lines')) {
        map.setPaintProperty('fiber-lines', 'line-width', FIBER_WIDTH_EXPR)
        map.setPaintProperty('fiber-lines', 'line-opacity', FIBER_OPACITY_EXPR)
      }
      // Clear hover-highlight source
      const src = map.getSource('hover-highlight') as mapboxgl.GeoJSONSource | undefined
      src?.setData({ type: 'FeatureCollection', features: [] })
      // Remove channel marker
      if (channelMarkerRef.current) {
        channelMarkerRef.current.remove()
        channelMarkerRef.current = null
      }
      // Restore default incident marker pulse
      if (highlightedMarkerRef.current) {
        highlightedMarkerRef.current.style.animation = 'proto-incident-ring 2s ease-in-out infinite'
        highlightedMarkerRef.current = null
      }
    }, [])

    useImperativeHandle(ref, () => ({
      flyTo: (center: [number, number], zoom = 14) => {
        // When the sidebar is open, pad the right side so the target
        // centers in the visible map area rather than behind the panel.
        const sidebarW = !sidebarOpenRef.current ? 0 : getSidebarWidth(sidebarRef)
        mapRef.current?.flyTo({
          center,
          zoom,
          duration: 1500,
          padding: { top: 0, bottom: 0, left: 0, right: sidebarW },
        })
      },
      highlightFiber: (fiberId: string) => {
        const map = mapRef.current
        if (!map || !map.getLayer('fiber-lines')) return
        clearHighlightImpl()
        // Data-driven: highlighted fiber gets full width/opacity, others dimmed
        map.setPaintProperty('fiber-lines', 'line-width', [
          'interpolate',
          ['linear'],
          ['zoom'],
          10,
          ['case', ['==', ['get', 'id'], fiberId], 5, 1.5],
          12,
          ['case', ['==', ['get', 'id'], fiberId], 5, 2],
          14,
          ['case', ['==', ['get', 'id'], fiberId], 5, 2.5],
        ])
        map.setPaintProperty('fiber-lines', 'line-opacity', ['case', ['==', ['get', 'id'], fiberId], 1, 0.15])
        let tick = 0
        highlightTimerRef.current = window.setInterval(() => {
          if (!map.getLayer('fiber-lines')) return
          map.setPaintProperty('fiber-lines', 'line-opacity', [
            'case',
            ['==', ['get', 'id'], fiberId],
            0.5 + 0.5 * Math.abs(Math.sin(tick * 0.6)),
            0.15,
          ])
          tick++
        }, 200)
      },
      highlightSection: (sectionId: string) => {
        const map = mapRef.current
        if (!map) return
        clearHighlightImpl()
        const sec = sectionsRef.current?.find(s => s.id === sectionId)
        if (!sec) return
        const secFiber = findFiber(sec.fiberId, sec.direction)
        if (!secFiber) return
        const coords = getSectionCoords(secFiber, sec.startChannel, sec.endChannel)
        if (coords.length < 2) return
        const color = fiberColorsRef.current ? getFiberColor(secFiber, fiberColorsRef.current) : '#888'
        const src = map.getSource('hover-highlight') as mapboxgl.GeoJSONSource | undefined
        src?.setData({
          type: 'FeatureCollection',
          features: [
            {
              type: 'Feature',
              properties: { color },
              geometry: { type: 'LineString', coordinates: coords },
            },
          ],
        })
        // Pulse the glow layer
        let tick = 0
        highlightTimerRef.current = window.setInterval(() => {
          if (map.getLayer('hover-highlight-glow')) {
            map.setPaintProperty('hover-highlight-glow', 'line-opacity', 0.2 + 0.3 * Math.abs(Math.sin(tick * 0.6)))
          }
          tick++
        }, 200)
      },
      highlightIncident: (incidentId: string) => {
        clearHighlightImpl()
        const marker = markersRef.current.get(incidentId)
        if (!marker) return
        const dot = marker.getElement().firstElementChild as HTMLElement | null
        if (!dot) return
        highlightedMarkerRef.current = dot
        dot.style.animation = 'proto-incident-ring 0.6s ease-in-out infinite'
      },
      highlightStructure: (structureId: string, structures: Infrastructure[]) => {
        const map = mapRef.current
        if (!map) return
        clearHighlightImpl()
        const structure = structures.find(s => s.id === structureId)
        if (!structure) return
        const sFiber = findFiber(structure.fiberId, structure.direction ?? 0)
        const coords = sFiber ? getSectionCoords(sFiber, structure.startChannel, structure.endChannel) : []
        if (coords.length < 2) return
        const typeColor = COLORS.structure[structure.type as 'bridge' | 'tunnel']?.dot ?? COLORS.structure.bridge.dot
        const src = map.getSource('hover-highlight') as mapboxgl.GeoJSONSource | undefined
        src?.setData({
          type: 'FeatureCollection',
          features: [
            {
              type: 'Feature',
              properties: { color: typeColor },
              geometry: { type: 'LineString', coordinates: coords },
            },
          ],
        })
        let tick = 0
        highlightTimerRef.current = window.setInterval(() => {
          if (map.getLayer('hover-highlight-glow')) {
            map.setPaintProperty('hover-highlight-glow', 'line-opacity', 0.2 + 0.3 * Math.abs(Math.sin(tick * 0.6)))
          }
          tick++
        }, 200)
      },
      highlightChannel: (lng: number, lat: number) => {
        const map = mapRef.current
        if (!map) return
        clearHighlightImpl()
        const el = document.createElement('div')
        el.style.cssText = `
                width: 14px; height: 14px; border-radius: 50%;
                background-color: #3b82f6;
                border: 2px solid #fff;
                animation: proto-channel-pulse 2s ease-in-out infinite;
            `
        channelMarkerRef.current = new mapboxgl.Marker({ element: el, anchor: 'center' })
          .setLngLat([lng, lat])
          .addTo(map)
      },
      clearHighlight: clearHighlightImpl,
    }))

    // Initialize map once
    useEffect(() => {
      if (!containerRef.current || mapRef.current) return

      mapboxgl.accessToken = MAPBOX_TOKEN

      const map = new mapboxgl.Map({
        container: containerRef.current,
        style: 'mapbox://styles/mapbox/dark-v11',
        center: MAP_CENTER,
        zoom: MAP_ZOOM,
        pitch: 30,
        antialias: false,
        fadeDuration: 0,
      })

      mapRef.current = map

      map.on('load', () => {
        // ── Fiber route layers (single merged source, simplified geometry) ──
        const fiberFeatures: GeoJSON.Feature[] = []
        for (const fiber of fibers) {
          const coords = fiberRenderCache.get(fiber.id)
          if (!coords) continue
          fiberFeatures.push({
            type: 'Feature' as const,
            properties: { id: fiber.id, name: fiber.name, color: fiber.color },
            geometry: { type: 'LineString' as const, coordinates: coords },
          })
        }
        map.addSource('fibers', {
          type: 'geojson',
          data: { type: 'FeatureCollection', features: fiberFeatures },
        })
        map.addLayer({
          id: 'fiber-lines',
          type: 'line',
          source: 'fibers',
          paint: {
            'line-color': ['get', 'color'],
            'line-width': ['interpolate', ['linear'], ['zoom'], 10, 1.5, 12, 2, 14, 2.5],
            'line-opacity': ['interpolate', ['linear'], ['zoom'], 10, 0.5, 12.5, 0.7, 14, 0.8],
          },
        })

        // ── Channel helper dots (one dot per channel for selection aid) ──
        const channelFeatures: GeoJSON.Feature[] = []
        for (const fiber of fibers) {
          const coords = fiberOffsetCache.get(fiber.id)
          if (!coords) continue
          for (let ch = 0; ch < coords.length; ch++) {
            const c = coords[ch]
            if (c[0] == null || c[1] == null) continue
            channelFeatures.push({
              type: 'Feature',
              properties: { color: fiber.color },
              geometry: { type: 'Point', coordinates: [c[0], c[1]] },
            })
          }
        }
        map.addSource('channel-helper', {
          type: 'geojson',
          data: { type: 'FeatureCollection', features: channelFeatures },
        })
        map.addLayer({
          id: 'channel-helper-dots',
          type: 'circle',
          source: 'channel-helper',
          layout: { visibility: 'none' },
          paint: {
            'circle-radius': ['interpolate', ['linear'], ['zoom'], 10, 1, 14, 2.5, 17, 4],
            'circle-color': ['get', 'color'],
            'circle-opacity': 0.6,
          },
        })

        // ── Vehicle dots source (layer added later, after sections) ──
        map.addSource('vehicles', {
          type: 'geojson',
          data: { type: 'FeatureCollection', features: [] },
        })

        // ── Section highlight source ─────────────────────────────
        map.addSource('section-highlights', {
          type: 'geojson',
          data: { type: 'FeatureCollection', features: [] },
        })

        map.addLayer({
          id: 'section-highlight-layer',
          type: 'line',
          source: 'section-highlights',
          minzoom: 12.5,
          layout: { visibility: 'none' },
          paint: {
            'line-color': ['get', 'color'],
            'line-width': 6,
            'line-opacity': 0.35,
          },
        })

        // ── Hover highlight source (for section/fiber hover from sidebar) ──
        map.addSource('hover-highlight', {
          type: 'geojson',
          data: { type: 'FeatureCollection', features: [] },
        })

        map.addLayer({
          id: 'hover-highlight-glow',
          type: 'line',
          source: 'hover-highlight',
          paint: {
            'line-color': '#ffffff',
            'line-width': 14,
            'line-opacity': 0.4,
            'line-blur': 7,
          },
        })

        map.addLayer({
          id: 'hover-highlight-line',
          type: 'line',
          source: 'hover-highlight',
          paint: {
            'line-color': ['get', 'color'],
            'line-width': 5,
            'line-opacity': 1,
          },
        })

        // ── Vehicle dots (after sections so sections show through) ──
        map.addLayer({
          id: 'vehicle-dots',
          type: 'circle',
          source: 'vehicles',
          minzoom: 12.5,
          paint: {
            'circle-radius': 4,
            'circle-color': ['get', 'color'],
            'circle-opacity': ['get', 'opacity'],
            'circle-stroke-color': 'rgba(0,0,0,0.3)',
            'circle-stroke-width': 1,
          },
        })

        // ── Pending section preview source ───────────────────────
        map.addSource('pending-section', {
          type: 'geojson',
          data: { type: 'FeatureCollection', features: [] },
        })

        map.addLayer({
          id: 'pending-section-layer',
          type: 'line',
          source: 'pending-section',
          paint: {
            'line-color': COLORS.structure.bridge.dot,
            'line-width': 4,
            'line-opacity': 0.6,
            'line-dasharray': [2, 2],
          },
        })

        // ── Pending point marker source ──────────────────────────
        map.addSource('pending-point', {
          type: 'geojson',
          data: { type: 'FeatureCollection', features: [] },
        })

        map.addLayer({
          id: 'pending-point-layer',
          type: 'circle',
          source: 'pending-point',
          paint: {
            'circle-radius': 6,
            'circle-color': COLORS.structure.bridge.dot,
            'circle-stroke-color': '#fff',
            'circle-stroke-width': 2,
          },
        })

        // ── Structure segment lines ──────────────────────────
        map.addSource('structure-lines', {
          type: 'geojson',
          data: { type: 'FeatureCollection', features: [] },
        })

        map.addLayer({
          id: 'structure-lines-layer',
          type: 'line',
          source: 'structure-lines',
          paint: {
            'line-color': ['get', 'color'],
            'line-width': 4,
            'line-opacity': 0.6,
          },
        })

        // ── Overview speed-section lines (zoom-driven fade) ────
        map.addSource('speed-sections', {
          type: 'geojson',
          data: { type: 'FeatureCollection', features: [] },
        })

        map.addLayer({
          id: 'speed-section-lines',
          type: 'line',
          source: 'speed-sections',
          paint: {
            'line-color': ['get', 'color'],
            'line-width': ['interpolate', ['linear'], ['zoom'], 10, 2.5, 12, 3, 13, 3.5],
            'line-opacity': ['interpolate', ['linear'], ['zoom'], 10, 0.7, 12.5, 0.5, 13.5, 0],
          },
        })

        // ── 3D buildings layer (initially hidden) ─────────────────
        // Find the first symbol layer to insert buildings beneath labels,
        // and hide any default building layers from the style
        const layers = map.getStyle().layers ?? []
        let labelLayerId: string | undefined
        for (const layer of layers) {
          if (layer.type === 'symbol' && (layer as { layout?: { 'text-field'?: unknown } }).layout?.['text-field']) {
            if (!labelLayerId) labelLayerId = layer.id
          }
          // Hide default building layers from the base style
          if ((layer['source-layer'] === 'building' || layer.id.includes('building')) && layer.id !== '3d-buildings') {
            map.setLayoutProperty(layer.id, 'visibility', 'none')
          }
        }

        map.addLayer(
          {
            id: '3d-buildings',
            source: 'composite',
            'source-layer': 'building',
            filter: ['==', 'extrude', 'true'],
            type: 'fill-extrusion',
            minzoom: 12.5,
            paint: {
              'fill-extrusion-color': '#aaa',
              'fill-extrusion-height': ['interpolate', ['linear'], ['zoom'], 12.5, 0, 13, ['get', 'height']],
              'fill-extrusion-base': ['interpolate', ['linear'], ['zoom'], 12.5, 0, 13, ['get', 'min_height']],
              'fill-extrusion-opacity': ['interpolate', ['linear'], ['zoom'], 12.5, 0, 13, 0.4, 15, 0.6],
            },
            layout: {
              visibility: 'none',
            },
          },
          labelLayerId,
        )

        // ── Zoom listener for overview mode (logical only, visuals are zoom-interpolated) ──
        const OVERVIEW_ZOOM_THRESHOLD = 12.5

        map.on('zoom', () => {
          const zoom = map.getZoom()
          const shouldOverview = zoom < OVERVIEW_ZOOM_THRESHOLD

          if (shouldOverview === overviewRef.current) return
          overviewRef.current = shouldOverview

          if (shouldOverview) {
            // Clear vehicles when entering overview
            const src = map.getSource('vehicles') as mapboxgl.GeoJSONSource | undefined
            src?.setData({ type: 'FeatureCollection', features: [] })
            if (deckOverlayRef.current) {
              try {
                deckOverlayRef.current.setProps({ layers: [] })
              } catch {
                /* not ready */
              }
            }
          }

          // Hide/show vehicle & creation layers in overview mode
          const layerVis = shouldOverview ? 'none' : 'visible'
          for (const lid of ['vehicle-dots', 'pending-section-layer', 'pending-point-layer']) {
            if (map.getLayer(lid)) map.setLayoutProperty(lid, 'visibility', layerVis)
          }

          // Toggle fiber visibility based on overview + hideFibers setting
          if (hideFibersRef.current && map.getLayer('fiber-lines')) {
            map.setLayoutProperty('fiber-lines', 'visibility', shouldOverview ? 'none' : 'visible')
          }

          handlersRef.current.onOverviewChange?.(shouldOverview)
        })

        // ── Vehicle color accessor (stable reference for deck.gl diffing) ──
        let selectedVehicleId: string | null = null
        const getVehicleColor = (d: VehiclePosition): [number, number, number, number] => {
          if (d.id === selectedVehicleId) return [255, 255, 255, 220]
          const lookup = thresholdLookupRef.current
          const thresholds = lookup?.(d.fiberId, d.direction, d.channel)
          return getSpeedColorRGBA(d.detectionSpeed, d.opacity, thresholds)
        }

        // ── Vehicle popup ──
        const vehiclePopup = new mapboxgl.Popup({
          closeButton: false,
          closeOnClick: false,
          className: 'proto-vehicle-popup',
          maxWidth: '220px',
          offset: [0, -12],
        })

        function updateVehiclePopup(positions: VehiclePosition[]) {
          if (!selectedVehicleId) return
          const v = positions.find(p => p.id === selectedVehicleId)
          if (!v || v.opacity < 0.05) {
            dismissVehiclePopup()
            return
          }
          const fiber = findFiber(v.fiberId, v.direction)
          const fiberName = fiber?.name ?? v.fiberId
          const dir = v.direction === 0 ? '→' : '←'
          const lookup = thresholdLookupRef.current
          const thresholds = lookup?.(v.fiberId, v.direction, v.channel)
          const speedColor = getSpeedColor(v.detectionSpeed, thresholds)
          const vehicleLabel =
            v.carCount > 1 ? `${v.carCount} ${i18n.t('common.vehicles')}` : `1 ${i18n.t('common.vehicles')}`
          vehiclePopup
            .setLngLat([v.position[0], v.position[1]])
            .setHTML(
              `<div class="proto-vehicle-popup-body">` +
                `<div class="proto-vehicle-popup-speed" style="color:${speedColor}">${Math.round(v.detectionSpeed)} km/h</div>` +
                `<div class="proto-vehicle-popup-detail">${fiberName} ${dir} · ch ${v.channel}</div>` +
                `<div class="proto-vehicle-popup-detail">${vehicleLabel}</div>` +
                `</div>`,
            )
          if (!vehiclePopup.isOpen()) vehiclePopup.addTo(map)
        }

        function dismissVehiclePopup() {
          selectedVehicleId = null
          vehiclePopup.remove()
        }

        // ── Map click handler for section creation + channel selection + deselection ─
        map.on('click', e => {
          // Incident/vehicle click fires before map click — skip if
          // the user actually clicked one of those.
          if (incidentClickedRef.current) {
            incidentClickedRef.current = false
            return
          }
          if (vehicleClickedRef.current) {
            vehicleClickedRef.current = false
            return
          }
          // Clicked somewhere else — dismiss vehicle popup if open
          dismissVehiclePopup()
          if (!sectionCreationRef.current) {
            // Not in creation mode — try channel selection, else deselect
            const hit = findNearestFiberPoint([e.lngLat.lng, e.lngLat.lat])
            if (hit) {
              handlersRef.current.onChannelClick?.(hit)
            } else {
              handlersRef.current.onMapClick?.()
            }
            return
          }

          const hit = findNearestFiberPoint([e.lngLat.lng, e.lngLat.lat])
          if (!hit) return

          const pending = pendingPointRef.current
          if (!pending) {
            handlersRef.current.onFiberClick?.(hit)
          } else {
            if (hit.fiberId !== pending.fiberId) return

            const start = Math.min(pending.channel, hit.channel)
            const end = Math.max(pending.channel, hit.channel)
            if (end - start < 10) return

            handlersRef.current.onSectionComplete?.(pending.fiberId, pending.direction, start, end)
          }
        })

        // ── Mousemove handler for section creation preview ────────
        map.on('mousemove', e => {
          if (!sectionCreationRef.current) return
          const pending = pendingPointRef.current
          if (!pending) return

          const hit = findNearestFiberPoint([e.lngLat.lng, e.lngLat.lat])
          const sectionSource = map.getSource('pending-section') as mapboxgl.GeoJSONSource | undefined
          if (!sectionSource) return

          if (!hit || hit.fiberId !== pending.fiberId) {
            sectionSource.setData({ type: 'FeatureCollection', features: [] })
            return
          }

          const pendingFiber = findFiber(pending.fiberId, pending.direction)
          if (!pendingFiber) return
          const start = Math.min(pending.channel, hit.channel)
          const end = Math.max(pending.channel, hit.channel)
          const coords = getSectionCoords(pendingFiber, start, end)
          if (coords.length < 2) {
            sectionSource.setData({ type: 'FeatureCollection', features: [] })
            return
          }

          sectionSource.setData({
            type: 'FeatureCollection',
            features: [{ type: 'Feature', properties: {}, geometry: { type: 'LineString', coordinates: coords } }],
          })
        })

        // ── deck.gl overlay (lazily added only in vehicles mode) ──
        let deckOverlay: MapboxOverlay | null = null
        let deckAdded = false

        function ensureDeckOverlay() {
          if (!deckOverlay) {
            deckOverlay = new MapboxOverlay({
              interleaved: true,
              layers: [],
              onClick: info => {
                if (info.object) {
                  const v = info.object as VehiclePosition
                  selectedVehicleId = v.id
                  vehicleClickedRef.current = true
                  return true
                }
                return false
              },
            })
            deckOverlayRef.current = deckOverlay
          }
          if (!deckAdded) {
            map.addControl(deckOverlay as unknown as mapboxgl.IControl)
            deckAdded = true
          }
        }

        function removeDeckOverlay() {
          dismissVehiclePopup()
          if (deckOverlay && deckAdded) {
            try {
              deckOverlay.setProps({ layers: [] })
            } catch {
              /* not ready */
            }
            map.removeControl(deckOverlay as unknown as mapboxgl.IControl)
            deckAdded = false
          }
        }

        // Create cube geometry once
        if (!cubeRef.current) {
          cubeRef.current = new CubeGeometry()
        }

        // ── Start render loop ─────────────────────────────────────
        let lastFrameTime = performance.now()
        let deckHasLayers = false
        let lastOverviewUpdate = 0
        const OVERVIEW_THROTTLE_MS = 2000 // speed-section colors update every 2s
        let lastGeoJSON: GeoJSON.FeatureCollection | null = null
        let vehiclesCleared = false
        let rafId: number | null = null
        let slowInterval: ReturnType<typeof setInterval> | null = null
        let loopStopped = false
        // Cache for speed-section GeoJSON to avoid GC pressure
        let lastSpeedSectionsKey = ''
        let lastSpeedSectionsData: GeoJSON.FeatureCollection | null = null

        function updateSpeedSections() {
          const secs = sectionsRef.current ?? []
          const stats = liveStatsRef.current
          // Build a lightweight key to detect actual data changes
          const keyParts: string[] = []
          for (const sec of secs) {
            const live = stats?.get(sec.id)
            const speed = live?.avgSpeed != null ? live.avgSpeed : sec.avgSpeed
            keyParts.push(sec.id, ':', String(speed ?? ''), '|')
          }
          const key = keyParts.join('')
          if (key === lastSpeedSectionsKey) return // no change, skip allocation
          lastSpeedSectionsKey = key

          const fiberMap = sectionFibersRef.current
          const features = secs
            .map(sec => {
              const secFiber = fiberMap.get(sec.id)
              if (!secFiber) return null
              const coords = getSectionCoords(secFiber, sec.startChannel, sec.endChannel)
              if (coords.length < 2) return null
              const live = stats?.get(sec.id)
              const speed = live?.avgSpeed != null ? live.avgSpeed : sec.avgSpeed
              return {
                type: 'Feature' as const,
                properties: { color: getSpeedColor(speed, sec.speedThresholds) },
                geometry: { type: 'LineString' as const, coordinates: coords },
              }
            })
            .filter(Boolean)
          lastSpeedSectionsData = { type: 'FeatureCollection', features: features as GeoJSON.Feature[] }
          const source = map.getSource('speed-sections') as mapboxgl.GeoJSONSource | undefined
          source?.setData(lastSpeedSectionsData)
        }

        function renderTick() {
          const now = performance.now()
          const deltaMs = Math.min(now - lastFrameTime, 100) // cap to avoid huge jumps
          lastFrameTime = now

          // Update speed-section lines periodically
          if (now - lastOverviewUpdate >= OVERVIEW_THROTTLE_MS) {
            lastOverviewUpdate = now
            updateSpeedSections()
          }

          if (overviewRef.current) {
            // Overview mode: remove deck.gl overlay entirely to stop repaints
            if (deckHasLayers || deckAdded) {
              removeDeckOverlay()
              deckHasLayers = false
            }
            return
          }

          if (displayModeRef.current === 'dots') {
            // Dots mode: use Mapbox circle layer from buildGeoJSON
            vehiclesCleared = false
            const fn = buildGeoJSONRef.current
            if (fn) {
              const geojson = fn()
              // Skip setData if buildGeoJSON returned the same cached object
              if (geojson !== lastGeoJSON) {
                lastGeoJSON = geojson
                // Add per-section color to each feature
                const lookup = thresholdLookupRef.current
                if (lookup) {
                  for (const f of geojson.features) {
                    if (!f.properties) continue
                    const t = lookup(f.properties.fiberId, f.properties.direction, f.properties.channel)
                    f.properties.color = getSpeedColor(f.properties.speed, t)
                  }
                } else {
                  for (const f of geojson.features) {
                    if (!f.properties) continue
                    f.properties.color = getSpeedColor(f.properties.speed)
                  }
                }
                const source = map.getSource('vehicles') as mapboxgl.GeoJSONSource | undefined
                source?.setData(geojson)
              }
            }
            // Remove deck.gl overlay entirely in dots mode to stop repaints
            if (deckHasLayers || deckAdded) {
              removeDeckOverlay()
              deckHasLayers = false
            }
          } else {
            // Vehicles mode: clear circle source once, render 3D cubes at 60fps
            if (!vehiclesCleared) {
              const source = map.getSource('vehicles') as mapboxgl.GeoJSONSource | undefined
              source?.setData({ type: 'FeatureCollection', features: [] })
              vehiclesCleared = true
              lastGeoJSON = null
            }

            const tick = tickAndCollectRef.current
            if (tick && cubeRef.current) {
              const positions = tick(now, deltaMs)
              updateVehiclePopup(positions)
              // Skip deck.gl update when there are no vehicles and we already cleared
              if (positions.length === 0 && !deckHasLayers) {
                // Nothing to render — avoid triggering a Mapbox repaint
              } else {
                const layer = new SimpleMeshLayer({
                  id: 'proto-vehicle-3d',
                  data: positions,
                  mesh: cubeRef.current,
                  getPosition,
                  getColor: getVehicleColor,
                  getOrientation,
                  getScale,
                  sizeScale: 1,
                  pickable: true,
                  autoHighlight: false,
                })
                ensureDeckOverlay()
                try {
                  deckOverlay?.setProps({ layers: [layer] })
                } catch {
                  /* not ready */
                }
                deckHasLayers = positions.length > 0
              }
            }
          }
        }

        // Adaptive loop: 60fps rAF for vehicles, 10Hz for dots, 2Hz for overview
        let currentLoopMode: 'raf' | 'fast' | 'slow' | null = null

        function rafLoop() {
          if (loopStopped) return
          renderTick()
          rafId = requestAnimationFrame(rafLoop)
        }

        function stopCurrentLoop() {
          if (rafId !== null) {
            cancelAnimationFrame(rafId)
            rafId = null
          }
          if (slowInterval !== null) {
            clearInterval(slowInterval)
            slowInterval = null
          }
          currentLoopMode = null
        }

        function syncLoop() {
          let target: 'raf' | 'fast' | 'slow'
          if (overviewRef.current) {
            target = 'slow'
          } else if (displayModeRef.current === 'vehicles') {
            target = 'raf'
          } else {
            target = 'fast'
          }
          if (target === currentLoopMode) return
          stopCurrentLoop()
          currentLoopMode = target
          if (target === 'raf') {
            rafLoop()
          } else {
            slowInterval = setInterval(renderTick, target === 'fast' ? 100 : 500)
          }
        }

        // Start with a sync and re-check every 500ms
        syncLoop()
        const loopSyncInterval = setInterval(syncLoop, 500)

        // Store cleanup
        map.once('remove', () => {
          loopStopped = true
          if (rafId !== null) cancelAnimationFrame(rafId)
          if (slowInterval !== null) clearInterval(slowInterval)
          clearInterval(loopSyncInterval)
          vehiclePopup.remove()
        })
      })

      // ── ResizeObserver ──────────────────────────────────────
      let resizeRafId: number | null = null
      const scheduleResize = () => {
        if (resizeRafId !== null) return
        resizeRafId = requestAnimationFrame(() => {
          resizeRafId = null
          map.resize()
        })
      }

      const resizer = new ResizeObserver(() => scheduleResize())
      resizer.observe(containerRef.current)

      return () => {
        resizer.disconnect()
        if (resizeRafId !== null) cancelAnimationFrame(resizeRafId)
        markersRef.current.forEach(m => m.remove())
        markersRef.current = new Map()
        map.remove()
        mapRef.current = null
        deckOverlayRef.current = null
      }
    }, [])

    // ── Update section highlights when sections change ────────────
    function updateSectionHighlights(map: mapboxgl.Map, secs: Section[]) {
      const source = map.getSource('section-highlights') as mapboxgl.GeoJSONSource | undefined
      if (!source) return
      source.setData(buildSectionHighlightData(secs, sectionFibersRef.current, fiberColorsRef.current))
    }

    useEffect(() => {
      const map = mapRef.current
      if (!map) return

      const apply = () => updateSectionHighlights(map, sections ?? [])

      // Apply immediately (works when sources are ready)
      apply()

      // Always also apply on next idle — covers races where getSource() returns
      // undefined during flyTo transitions or style reloads
      const onIdle = () => apply()
      map.once('idle', onIdle)
      return () => {
        map.off('idle', onIdle)
      }
    }, [sections, fiberColors])

    // ── Update pending point marker ──────────────────────────────
    useEffect(() => {
      const map = mapRef.current
      if (!map) return

      const apply = () => {
        const pointSource = map.getSource('pending-point') as mapboxgl.GeoJSONSource | undefined
        if (!pointSource) return

        if (pendingPoint) {
          pointSource.setData({
            type: 'FeatureCollection',
            features: [
              {
                type: 'Feature',
                properties: {},
                geometry: { type: 'Point', coordinates: [pendingPoint.lng, pendingPoint.lat] },
              },
            ],
          })
        } else {
          pointSource.setData({ type: 'FeatureCollection', features: [] })
        }

        const sectionSource = map.getSource('pending-section') as mapboxgl.GeoJSONSource | undefined
        if (sectionSource && !pendingPoint) {
          sectionSource.setData({ type: 'FeatureCollection', features: [] })
        }
      }

      if (map.isStyleLoaded()) {
        apply()
      } else {
        map.once('idle', apply)
        return () => {
          map.off('idle', apply)
        }
      }
    }, [pendingPoint])

    // ── Update fiber line colors when fiberColors change ──────────
    useEffect(() => {
      const map = mapRef.current
      if (!map || !fiberColors) return
      const src = map.getSource('fibers') as mapboxgl.GeoJSONSource | undefined
      if (!src) return
      const features: GeoJSON.Feature[] = []
      for (const fiber of fibers) {
        const coords = fiberRenderCache.get(fiber.id)
        if (!coords) continue
        features.push({
          type: 'Feature' as const,
          properties: { id: fiber.id, name: fiber.name, color: getFiberColor(fiber, fiberColors) },
          geometry: { type: 'LineString' as const, coordinates: coords },
        })
      }
      src.setData({ type: 'FeatureCollection', features })
    }, [fiberColors])

    // ── Update structure lines when structures/showStructuresOnMap change ──
    useEffect(() => {
      const map = mapRef.current
      if (!map) return

      const apply = () => {
        const src = map.getSource('structure-lines') as mapboxgl.GeoJSONSource | undefined
        if (!src) return

        if (!showStructuresOnMap || !structures?.length) {
          src.setData({ type: 'FeatureCollection', features: [] })
          return
        }

        const features = structures
          .map(s => {
            const sFiber = findFiber(s.fiberId, s.direction ?? 0)
            const coords = sFiber ? getSectionCoords(sFiber, s.startChannel, s.endChannel) : []
            if (coords.length < 2) return null
            const color = COLORS.structure[s.type as 'bridge' | 'tunnel']?.dot ?? COLORS.structure.bridge.dot
            return {
              type: 'Feature' as const,
              properties: { color, id: s.id },
              geometry: { type: 'LineString' as const, coordinates: coords },
            }
          })
          .filter(Boolean)

        src.setData({ type: 'FeatureCollection', features: features as GeoJSON.Feature[] })
      }

      apply()
      map.once('idle', apply)
      return () => {
        map.off('idle', apply)
      }
    }, [structures, showStructuresOnMap])

    // ── Update structure label markers ──────────────────────────
    useEffect(() => {
      const map = mapRef.current
      if (!map) return

      // Remove existing markers
      structureMarkersRef.current.forEach(m => m.remove())
      structureMarkersRef.current = new Map()

      if (!showStructureLabels || !structures?.length) return

      const shmStatusColors = shmStatusColorsMap

      for (const s of structures) {
        const sFiber = findFiber(s.fiberId, s.direction ?? 0)
        const midChannel = Math.floor((s.startChannel + s.endChannel) / 2)
        const coord = sFiber ? channelToCoord(sFiber, midChannel) : null
        if (!coord) continue

        const status = structureStatuses?.get(s.id)
        const statusDotColor = status ? (shmStatusColors[status.status] ?? COLORS.shmChart.axis) : COLORS.shmChart.axis
        const isSelected = selectedStructureId === s.id

        const imageHtml = s.imageUrl
          ? `<img src="${s.imageUrl}" style="width:100%;height:48px;object-fit:cover;border-radius:6px 6px 0 0;display:block;" />`
          : ''

        const el = document.createElement('div')
        el.className = 'prototype'
        el.innerHTML = `
                <div style="
                    background: var(--proto-surface, #1e293b);
                    border: 1px solid ${isSelected ? 'var(--proto-accent, #6366f1)' : 'var(--proto-border, #334155)'};
                    border-radius: 8px;
                    cursor: pointer;
                    overflow: hidden;
                    box-shadow: 0 4px 12px rgba(0,0,0,0.4);
                    white-space: nowrap;
                    min-width: 100px;
                    max-width: 160px;
                ">
                    ${imageHtml}
                    <div style="padding:6px 10px;display:flex;align-items:center;gap:6px;">
                        <span style="width:6px;height:6px;border-radius:50%;background:${statusDotColor};flex-shrink:0;"></span>
                        <span style="font-size:11px;color:#e2e8f0;font-weight:500;overflow:hidden;text-overflow:ellipsis;">${s.name}</span>
                        <span style="font-size:10px;color:#64748b;flex-shrink:0;">${s.type}</span>
                    </div>
                </div>
            `

        el.addEventListener('click', e => {
          e.stopPropagation()
          onStructureClickRef.current?.(s.id)
        })

        const marker = new mapboxgl.Marker({ element: el, anchor: 'bottom' }).setLngLat(coord).addTo(map)
        structureMarkersRef.current.set(s.id, marker)
      }

      return () => {
        structureMarkersRef.current.forEach(m => m.remove())
        structureMarkersRef.current = new Map()
      }
    }, [structures, structureStatuses, showStructureLabels, selectedStructureId])

    // ── Update incident markers when incidents prop changes ──────
    useEffect(() => {
      const map = mapRef.current
      if (!map) return

      // Remove old markers
      markersRef.current.forEach(m => m.remove())
      markersRef.current = new Map()

      if (!incidents?.length) return

      for (const inc of incidents) {
        if (inc.resolved) continue

        const lngLat: [number, number] = inc.location
        const color = severityColor[inc.severity]

        const el = document.createElement('div')
        el.style.cssText = `
                width: 20px; height: 20px; border-radius: 50%;
                display: flex; align-items: center; justify-content: center;
                cursor: pointer;
                background: rgba(30, 30, 40, 0.75);
                border: 2px solid ${color};
                box-shadow: 0 0 8px rgba(0,0,0,0.5);
            `
        const dot = document.createElement('div')
        dot.style.cssText = `
                width: 8px; height: 8px; border-radius: 50%;
                background-color: ${color};
                box-shadow: 0 0 6px ${color}cc;
            `
        dot.style.animation = 'proto-incident-ring 2s ease-in-out infinite'
        el.appendChild(dot)
        el.title = inc.title

        el.addEventListener('click', e => {
          e.stopPropagation()
          incidentClickedRef.current = true
          handlersRef.current.onIncidentClick?.(inc.id)
        })

        const marker = new mapboxgl.Marker({ element: el, anchor: 'center' }).setLngLat(lngLat).addTo(map)
        markersRef.current.set(inc.id, marker)
      }
    }, [incidents])

    // ── Hide/show fiber lines in overview mode ─────────────────
    useEffect(() => {
      const map = mapRef.current
      if (!map || !map.isStyleLoaded()) return
      const hide = hideFibersInOverview && overviewRef.current
      if (map.getLayer('fiber-lines')) {
        map.setLayoutProperty('fiber-lines', 'visibility', hide ? 'none' : 'visible')
      }
    }, [hideFibersInOverview])

    // ── Toggle 3D buildings layer ─────────────────────────────────
    useEffect(() => {
      const map = mapRef.current
      if (!map || !map.isStyleLoaded()) return
      if (map.getLayer('3d-buildings')) {
        map.setLayoutProperty('3d-buildings', 'visibility', show3DBuildings ? 'visible' : 'none')
      }
    }, [show3DBuildings])

    // ── Toggle channel helper dots ───────────────────────────────
    useEffect(() => {
      const map = mapRef.current
      if (!map || !map.isStyleLoaded()) return
      if (map.getLayer('channel-helper-dots')) {
        map.setLayoutProperty('channel-helper-dots', 'visibility', showChannelHelper ? 'visible' : 'none')
      }
    }, [showChannelHelper])

    // ── Map cursor in creation mode ──────────────────────────────
    useEffect(() => {
      const map = mapRef.current
      if (!map) return
      map.getCanvas().style.cursor = sectionCreationMode ? 'crosshair' : ''
    }, [sectionCreationMode])

    return (
      <div className="relative w-full h-full">
        <div ref={containerRef} className="w-full h-full" />
      </div>
    )
  }),
)
