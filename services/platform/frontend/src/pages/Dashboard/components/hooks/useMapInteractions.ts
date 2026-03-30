import { useEffect } from 'react'
import type { Map as MapboxMap, GeoJSONSource, MapMouseEvent } from 'mapbox-gl'
import type { MapboxOverlay } from '@deck.gl/mapbox'
import type { Fiber, PendingPoint } from '../../types'
import type { CoverageRange } from '@/api/fibers'
import { MAP_SOURCES, MAP_LAYERS, type MapHandlers } from './mapTypes'
import { onMapReady } from '../mapUtils'

interface UseMapInteractionsParams {
  mapRef: React.RefObject<MapboxMap | null>
  handlersRef: React.RefObject<MapHandlers>
  pendingPointRef: React.RefObject<PendingPoint | null | undefined>
  sectionCreationRef: React.RefObject<boolean | undefined>
  incidentClickedRef: React.MutableRefObject<boolean>
  vehicleClickedRef: React.MutableRefObject<boolean>
  overviewRef: React.MutableRefObject<boolean>
  hideFibersRef: React.RefObject<boolean | undefined>
  deckOverlayRef: React.RefObject<MapboxOverlay | null>
  coverageFilterRef: React.RefObject<Map<string, CoverageRange[]> | undefined>
  dismissVehiclePopup: () => void
  findNearestFiberPointRef: React.RefObject<
    (
      lngLat: [number, number],
      maxDistDeg?: number,
      coverageFilter?: Map<string, CoverageRange[]>,
    ) => { fiberId: string; direction: 0 | 1; channel: number; lng: number; lat: number } | null
  >
  findFiberRef: React.RefObject<(cableId: string, direction: number) => Fiber | undefined>
  getSectionCoordsRef: React.RefObject<(fiber: Fiber, startChannel: number, endChannel: number) => [number, number][]>
}

export function useMapInteractions({
  mapRef,
  handlersRef,
  pendingPointRef,
  sectionCreationRef,
  incidentClickedRef,
  vehicleClickedRef,
  overviewRef,
  hideFibersRef,
  deckOverlayRef,
  coverageFilterRef,
  dismissVehiclePopup,
  findNearestFiberPointRef,
  findFiberRef,
  getSectionCoordsRef,
}: UseMapInteractionsParams) {
  useEffect(() => {
    return onMapReady(mapRef, map => {
      // ── Zoom listener for overview mode ──
      const OVERVIEW_ZOOM_THRESHOLD = 12.5

      const onZoom = () => {
        const zoom = map.getZoom()
        const shouldOverview = zoom < OVERVIEW_ZOOM_THRESHOLD

        if (shouldOverview === overviewRef.current) return
        overviewRef.current = shouldOverview

        if (shouldOverview) {
          const src = map.getSource(MAP_SOURCES.vehicles) as GeoJSONSource | undefined
          src?.setData({ type: 'FeatureCollection', features: [] })
          if (deckOverlayRef.current) {
            try {
              deckOverlayRef.current.setProps({ layers: [] })
            } catch {
              /* not ready */
            }
          }
        }

        const layerVis = shouldOverview ? 'none' : 'visible'
        for (const lid of [MAP_LAYERS.vehicleDots, MAP_LAYERS.pendingSection, MAP_LAYERS.pendingPoint]) {
          if (map.getLayer(lid)) map.setLayoutProperty(lid, 'visibility', layerVis)
        }

        if (hideFibersRef.current && map.getLayer(MAP_LAYERS.fiberLines)) {
          map.setLayoutProperty(MAP_LAYERS.fiberLines, 'visibility', shouldOverview ? 'none' : 'visible')
        }

        handlersRef.current.onOverviewChange?.(shouldOverview)
      }

      // ── Map click handler ──
      const onClick = (e: MapMouseEvent) => {
        if (incidentClickedRef.current) {
          incidentClickedRef.current = false
          return
        }
        if (vehicleClickedRef.current) {
          vehicleClickedRef.current = false
          return
        }
        dismissVehiclePopup()
        const coverage = coverageFilterRef.current
        if (!sectionCreationRef.current) {
          const hit = findNearestFiberPointRef.current([e.lngLat.lng, e.lngLat.lat], undefined, coverage)
          if (hit) {
            handlersRef.current.onChannelClick?.(hit)
          } else {
            handlersRef.current.onMapClick?.()
          }
          return
        }

        const hit = findNearestFiberPointRef.current([e.lngLat.lng, e.lngLat.lat], undefined, coverage)
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
      }

      // ── Mousemove handler for section creation preview ──
      const onMouseMove = (e: MapMouseEvent) => {
        if (!sectionCreationRef.current) return
        const pending = pendingPointRef.current
        if (!pending) return

        const hit = findNearestFiberPointRef.current([e.lngLat.lng, e.lngLat.lat], undefined, coverageFilterRef.current)
        const sectionSource = map.getSource(MAP_SOURCES.pendingSection) as GeoJSONSource | undefined
        if (!sectionSource) return

        if (!hit || hit.fiberId !== pending.fiberId) {
          sectionSource.setData({ type: 'FeatureCollection', features: [] })
          return
        }

        const pendingFiber = findFiberRef.current(pending.fiberId, pending.direction)
        if (!pendingFiber) return
        const start = Math.min(pending.channel, hit.channel)
        const end = Math.max(pending.channel, hit.channel)
        const coords = getSectionCoordsRef.current(pendingFiber, start, end)
        if (coords.length < 2) {
          sectionSource.setData({ type: 'FeatureCollection', features: [] })
          return
        }

        sectionSource.setData({
          type: 'FeatureCollection',
          features: [{ type: 'Feature', properties: {}, geometry: { type: 'LineString', coordinates: coords } }],
        })
      }

      map.on('zoom', onZoom)
      map.on('click', onClick)
      map.on('mousemove', onMouseMove)

      return () => {
        map.off('zoom', onZoom)
        map.off('click', onClick)
        map.off('mousemove', onMouseMove)
      }
    })
  }, [
    mapRef,
    handlersRef,
    pendingPointRef,
    sectionCreationRef,
    incidentClickedRef,
    vehicleClickedRef,
    overviewRef,
    hideFibersRef,
    deckOverlayRef,
    coverageFilterRef,
    dismissVehiclePopup,
    findNearestFiberPointRef,
    findFiberRef,
    getSectionCoordsRef,
  ])
}
