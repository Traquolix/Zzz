import { useEffect, useRef } from 'react'
import type { Map as MapboxMap, IControl, GeoJSONSource } from 'mapbox-gl'
import type { MapboxOverlay } from '@deck.gl/mapbox'
import { getSpeedColor, getSpeedColorRGBA } from '../../data'
import type { Fiber, Section, LiveSectionStats, SpeedThresholds } from '../../types'
import type { VehiclePosition } from '../../hooks/useVehicleSim'
import { getPosition, getOrientation, getScale, onMapReady } from '../mapUtils'
import { MAP_SOURCES } from './mapTypes'

// MapboxOverlay implements IControl at runtime, but @deck.gl/mapbox types don't declare it.
const asControl = (overlay: MapboxOverlay) => overlay as unknown as IControl

// Lazy-loaded deck.gl/luma.gl modules — only fetched when vehicles mode is first activated.
type DeckModules = {
  MapboxOverlay: typeof import('@deck.gl/mapbox').MapboxOverlay
  SimpleMeshLayer: typeof import('@deck.gl/mesh-layers').SimpleMeshLayer
  CubeGeometry: typeof import('@luma.gl/engine').CubeGeometry
}
let deckModulesPromise: Promise<DeckModules> | null = null
function loadDeckModules(): Promise<DeckModules> {
  if (!deckModulesPromise) {
    deckModulesPromise = Promise.all([
      import('@deck.gl/mapbox'),
      import('@deck.gl/mesh-layers'),
      import('@luma.gl/engine'),
    ]).then(([mapbox, mesh, luma]) => ({
      MapboxOverlay: mapbox.MapboxOverlay,
      SimpleMeshLayer: mesh.SimpleMeshLayer,
      CubeGeometry: luma.CubeGeometry,
    }))
  }
  return deckModulesPromise
}

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
  getSectionCoordsRef: React.RefObject<(fiber: Fiber, startChannel: number, endChannel: number) => [number, number][]>
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
  getSectionCoordsRef,
}: UseRenderLoopParams) {
  const vehicleClickedRef = useRef(false)
  const deckOverlayRef = useRef<MapboxOverlay | null>(null)
  const vehiclePopupRef = useRef(vehiclePopup)
  vehiclePopupRef.current = vehiclePopup

  useEffect(() => {
    return onMapReady(mapRef, map => {
      // ── Vehicle color accessor (stable reference for deck.gl diffing) ──
      const getVehicleColor = (d: VehiclePosition): [number, number, number, number] => {
        if (vehiclePopupRef.current.isSelected(d.id)) return [255, 255, 255, 220]
        const lookup = thresholdLookupRef.current
        const thresholds = lookup?.(d.fiberId, d.direction, d.channel)
        return getSpeedColorRGBA(d.detectionSpeed, d.opacity, thresholds)
      }

      // ── deck.gl modules (lazy-loaded on first vehicles mode activation) ──
      let deck: DeckModules | null = null
      let deckLoading = false
      let deckOverlay: MapboxOverlay | null = null
      let deckAdded = false
      let cubeGeometry: InstanceType<DeckModules['CubeGeometry']> | null = null

      function ensureDeckModules() {
        if (deck || deckLoading) return
        deckLoading = true
        loadDeckModules().then(modules => {
          if (loopStopped) return
          deck = modules
          cubeGeometry = new modules.CubeGeometry()
        })
      }

      function ensureDeckOverlay() {
        if (!deck) return
        if (!deckOverlay) {
          deckOverlay = new deck.MapboxOverlay({
            interleaved: true,
            layers: [],
            onClick: info => {
              if (info.object) {
                const v = info.object as VehiclePosition
                vehiclePopupRef.current.select(v.id)
                vehicleClickedRef.current = true
                return true
              }
              return false
            },
          })
          deckOverlayRef.current = deckOverlay
        }
        if (!deckAdded) {
          map.addControl(asControl(deckOverlay))
          deckAdded = true
        }
      }

      function removeDeckOverlay() {
        vehiclePopupRef.current.dismiss()
        if (deckOverlay && deckAdded) {
          try {
            deckOverlay.setProps({ layers: [] })
          } catch {
            /* not ready */
          }
          map.removeControl(asControl(deckOverlay))
          deckAdded = false
        }
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
            const coords = getSectionCoordsRef.current(secFiber, sec.startChannel, sec.endChannel)
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
        const source = map.getSource(MAP_SOURCES.speedSections) as GeoJSONSource | undefined
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
              const source = map.getSource(MAP_SOURCES.vehicles) as GeoJSONSource | undefined
              source?.setData(geojson)
            }
          }
          if (deckHasLayers || deckAdded) {
            removeDeckOverlay()
            deckHasLayers = false
          }
        } else {
          // Start loading deck.gl modules as soon as vehicles mode is entered
          ensureDeckModules()

          if (!vehiclesCleared) {
            const source = map.getSource(MAP_SOURCES.vehicles) as GeoJSONSource | undefined
            source?.setData({ type: 'FeatureCollection', features: [] })
            vehiclesCleared = true
            lastGeoJSON = null
          }

          const tick = tickAndCollectRef.current
          if (tick && deck && cubeGeometry) {
            const positions = tick(now, deltaMs)
            vehiclePopupRef.current.update(positions)
            if (positions.length === 0 && !deckHasLayers) {
              // Nothing to render
            } else {
              const layer = new deck.SimpleMeshLayer({
                id: 'dash-vehicle-3d',
                data: positions,
                mesh: cubeGeometry,
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

      return () => {
        loopStopped = true
        stopCurrentLoop()
        clearInterval(loopSyncInterval)
        vehiclePopupRef.current.cleanup()
        if (deckOverlay && deckAdded) {
          try {
            map.removeControl(asControl(deckOverlay))
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
    getSectionCoordsRef,
  ])

  return {
    vehicleClickedRef,
    deckOverlayRef,
  }
}
