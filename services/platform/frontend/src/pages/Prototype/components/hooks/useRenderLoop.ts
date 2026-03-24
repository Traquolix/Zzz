import { useEffect, useRef } from 'react'
import type { Map as MapboxMap, IControl, GeoJSONSource } from 'mapbox-gl'
import { MapboxOverlay } from '@deck.gl/mapbox'
import { SimpleMeshLayer } from '@deck.gl/mesh-layers'
import { CubeGeometry } from '@luma.gl/engine'
import { getSpeedColor, getSectionCoords, getSpeedColorRGBA } from '../../data'
import type { Fiber, Section, LiveSectionStats, SpeedThresholds } from '../../types'
import type { VehiclePosition } from '../../hooks/useVehicleSim'
import { getPosition, getOrientation, getScale, onMapReady } from '../mapUtils'

interface UseRenderLoopParams {
  mapRef: React.RefObject<MapboxMap | null>
  overviewRef: React.MutableRefObject<boolean>
  displayModeRef: React.RefObject<'dots' | 'vehicles'>
  buildGeoJSONRef: React.RefObject<(() => GeoJSON.FeatureCollection) | undefined>
  tickAndCollectRef: React.RefObject<((now: number, deltaMs: number) => VehiclePosition[]) | undefined>
  liveStatsRef: React.RefObject<Map<string, LiveSectionStats> | undefined>
  sectionsRef: React.RefObject<Section[] | undefined>
  sectionFibersRef: React.RefObject<Map<string, Fiber>>
  thresholdLookupRef: React.RefObject<
    ((cableId: string, direction: 0 | 1, channel: number) => SpeedThresholds) | undefined
  >
  vehiclePopup: {
    update: (positions: VehiclePosition[]) => void
    select: (vehicleId: string) => void
    isSelected: (vehicleId: string) => boolean
    dismiss: () => void
    cleanup: () => void
  }
}

export function useRenderLoop({
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
}: UseRenderLoopParams) {
  const vehicleClickedRef = useRef(false)
  const deckOverlayRef = useRef<MapboxOverlay | null>(null)
  const cubeRef = useRef<CubeGeometry | null>(null)

  useEffect(() => {
    return onMapReady(mapRef, map => {
      // ── Vehicle color accessor (stable reference for deck.gl diffing) ──
      const getVehicleColor = (d: VehiclePosition): [number, number, number, number] => {
        if (vehiclePopup.isSelected(d.id)) return [255, 255, 255, 220]
        const lookup = thresholdLookupRef.current
        const thresholds = lookup?.(d.fiberId, d.direction, d.channel)
        return getSpeedColorRGBA(d.detectionSpeed, d.opacity, thresholds)
      }

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
                vehiclePopup.select(v.id)
                vehicleClickedRef.current = true
                return true
              }
              return false
            },
          })
          deckOverlayRef.current = deckOverlay
        }
        if (!deckAdded) {
          map.addControl(deckOverlay as unknown as IControl)
          deckAdded = true
        }
      }

      function removeDeckOverlay() {
        vehiclePopup.dismiss()
        if (deckOverlay && deckAdded) {
          try {
            deckOverlay.setProps({ layers: [] })
          } catch {
            /* not ready */
          }
          map.removeControl(deckOverlay as unknown as IControl)
          deckAdded = false
        }
      }

      // Create cube geometry once
      if (!cubeRef.current) {
        cubeRef.current = new CubeGeometry()
      }

      // ── Render loop state ──
      let lastFrameTime = performance.now()
      let deckHasLayers = false
      let lastOverviewUpdate = 0
      const OVERVIEW_THROTTLE_MS = 2000
      let lastGeoJSON: GeoJSON.FeatureCollection | null = null
      let vehiclesCleared = false
      let rafId: number | null = null
      let slowInterval: ReturnType<typeof setInterval> | null = null
      let loopStopped = false
      let lastSpeedSectionsKey = ''

      function updateSpeedSections() {
        const secs = sectionsRef.current ?? []
        const stats = liveStatsRef.current
        const keyParts: string[] = []
        for (const sec of secs) {
          const live = stats?.get(sec.id)
          const speed = live?.avgSpeed != null ? live.avgSpeed : sec.avgSpeed
          keyParts.push(sec.id, ':', String(speed ?? ''), '|')
        }
        const key = keyParts.join('')
        if (key === lastSpeedSectionsKey) return
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
        const data: GeoJSON.FeatureCollection = {
          type: 'FeatureCollection',
          features: features as GeoJSON.Feature[],
        }
        const source = map.getSource('speed-sections') as GeoJSONSource | undefined
        source?.setData(data)
      }

      function renderTick() {
        const now = performance.now()
        const deltaMs = Math.min(now - lastFrameTime, 100)
        lastFrameTime = now

        if (now - lastOverviewUpdate >= OVERVIEW_THROTTLE_MS) {
          lastOverviewUpdate = now
          updateSpeedSections()
        }

        if (overviewRef.current) {
          if (deckHasLayers || deckAdded) {
            removeDeckOverlay()
            deckHasLayers = false
          }
          return
        }

        if (displayModeRef.current === 'dots') {
          vehiclesCleared = false
          const fn = buildGeoJSONRef.current
          if (fn) {
            const geojson = fn()
            if (geojson !== lastGeoJSON) {
              lastGeoJSON = geojson
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
              const source = map.getSource('vehicles') as GeoJSONSource | undefined
              source?.setData(geojson)
            }
          }
          if (deckHasLayers || deckAdded) {
            removeDeckOverlay()
            deckHasLayers = false
          }
        } else {
          if (!vehiclesCleared) {
            const source = map.getSource('vehicles') as GeoJSONSource | undefined
            source?.setData({ type: 'FeatureCollection', features: [] })
            vehiclesCleared = true
            lastGeoJSON = null
          }

          const tick = tickAndCollectRef.current
          if (tick && cubeRef.current) {
            const positions = tick(now, deltaMs)
            vehiclePopup.update(positions)
            if (positions.length === 0 && !deckHasLayers) {
              // Nothing to render
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

      syncLoop()
      const loopSyncInterval = setInterval(syncLoop, 500)

      map.once('remove', () => {
        loopStopped = true
        if (rafId !== null) cancelAnimationFrame(rafId)
        if (slowInterval !== null) clearInterval(slowInterval)
        clearInterval(loopSyncInterval)
      })

      return () => {
        loopStopped = true
        stopCurrentLoop()
        clearInterval(loopSyncInterval)
        vehiclePopup.cleanup()
        if (deckOverlay && deckAdded) {
          try {
            map.removeControl(deckOverlay as unknown as IControl)
          } catch {
            /* map may already be removed */
          }
        }
        deckOverlayRef.current = null
      }
    })
  }, [
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
  ])

  return {
    vehicleClickedRef,
    deckOverlayRef,
  }
}
