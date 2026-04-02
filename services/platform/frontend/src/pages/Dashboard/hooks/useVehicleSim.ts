import { useRef, useEffect, useCallback } from 'react'
import { VehicleSimEngine } from '@/lib/vehicleSim/engine'
import type { SensorEvent } from '@/lib/vehicleSim/types'
import { parseDetections } from '@/lib/parseMessage'
import { getFiberOffsetCoords } from '@/lib/geoUtils'
import { useRealtime } from '@/hooks/useRealtime'
import { useFlowReset } from '@/hooks/useFlowReset'
import type { Fiber } from '../types'

export interface VehiclePosition {
  id: string
  position: [number, number, number]
  angle: number
  speed: number
  detectionSpeed: number
  opacity: number
  fiberId: string // raw cable ID (e.g. "carros"), not the internal composite ID
  direction: 0 | 1
  channel: number
  carCount: number
  glrtMax: number
  strainPeak: number
  strainRms: number
  nTrucks: number
}

interface FiberEngine {
  cableId: string
  direction: 0 | 1
  engine: VehicleSimEngine
  coords: [number, number][]
  step: number
}

function getBearing(coords: [number, number][], index: number, direction: 0 | 1): number {
  if (coords.length < 2) return 0
  const i = Math.max(0, Math.min(coords.length - 2, Math.floor(index)))
  const [lng1, lat1] = coords[i]
  const [lng2, lat2] = coords[i + 1]
  const dLng = ((lng2 - lng1) * Math.PI) / 180
  const lat1R = (lat1 * Math.PI) / 180
  const lat2R = (lat2 * Math.PI) / 180
  const y = Math.sin(dLng) * Math.cos(lat2R)
  const x = Math.cos(lat1R) * Math.sin(lat2R) - Math.sin(lat1R) * Math.cos(lat2R) * Math.cos(dLng)
  const b = ((Math.atan2(y, x) * 180) / Math.PI + 360) % 360
  return direction === 0 ? b : (b + 180) % 360
}

function interpCoord(coords: [number, number][], index: number): [number, number] | null {
  if (coords.length < 2) return null
  const c = Math.max(0, Math.min(coords.length - 1, index))
  const i = Math.floor(c)
  const j = Math.min(i + 1, coords.length - 1)
  const t = c - i
  return [coords[i][0] + (coords[j][0] - coords[i][0]) * t, coords[i][1] + (coords[j][1] - coords[i][1]) * t]
}

export function useVehicleSim(fibers: Fiber[]): {
  tickAndCollect: (now: number, deltaMs: number) => VehiclePosition[]
} {
  const { subscribe } = useRealtime()
  const enginesRef = useRef<FiberEngine[]>([])

  // Clear all engine state on flow switch
  useFlowReset(() => {
    for (const fe of enginesRef.current) {
      fe.engine.reset()
    }
  })

  // Initialize engines when fibers change
  useEffect(() => {
    if (fibers.length === 0) return
    enginesRef.current = fibers.map(fiber => {
      const engine = new VehicleSimEngine({
        totalChannels: fiber.totalChannels,
        metersPerChannel: 5,
      })
      const coords = getFiberOffsetCoords({ ...fiber, coordinates: fiber.coordinates as [number, number][] })
      return {
        cableId: fiber.parentCableId,
        direction: fiber.direction,
        engine,
        coords,
        step: 1,
      }
    })
    return () => {
      for (const fe of enginesRef.current) fe.engine.reset()
      enginesRef.current = []
    }
  }, [fibers])

  // Subscribe to detections
  useEffect(() => {
    const unsub = subscribe('detections', (data: unknown) => {
      const detections = parseDetections(data)
      const now = performance.now()

      for (const d of detections) {
        const fe = enginesRef.current.find(e => e.cableId === d.fiberId && e.direction === d.direction)
        if (!fe) continue

        const event: SensorEvent = {
          channel: d.channel,
          speed: d.speed,
          count: d.count,
          direction: d.direction,
          glrtMax: d.glrtMax,
          strainPeak: d.strainPeak,
          strainRms: d.strainRms,
          nTrucks: d.nTrucks,
        }
        fe.engine.onSensorEvent(event, now)
      }
    })
    return unsub
  }, [subscribe])

  const tickAndCollect = useCallback((now: number, deltaMs: number): VehiclePosition[] => {
    const positions: VehiclePosition[] = []

    for (const fe of enginesRef.current) {
      fe.engine.tick(now, deltaMs)

      for (const track of fe.engine.tracks) {
        if (track.opacity <= 0) continue

        // Convert render position (raw channels) to coordinate index
        const coordIndex = track.renderPosition / fe.step
        const coord = interpCoord(fe.coords, coordIndex)
        if (!coord) continue

        const bearing = getBearing(fe.coords, coordIndex, fe.direction)
        const speed = fe.engine.getRenderSpeed(track)

        const detectionSpeed = fe.engine.getDetectionSpeed(track)
        const activeCarCount = track.cars.filter(c => c.state === 'active').length

        for (const car of track.cars) {
          if (car.opacity <= 0) continue
          positions.push({
            id: car.id,
            position: [coord[0], coord[1], 0],
            angle: bearing,
            speed,
            detectionSpeed,
            opacity: track.opacity * car.opacity,
            fiberId: fe.cableId,
            direction: fe.direction,
            channel: Math.round(track.renderPosition),
            carCount: activeCarCount,
            glrtMax: track.lastGlrtMax,
            strainPeak: track.lastStrainPeak,
            strainRms: track.lastStrainRms,
            nTrucks: track.lastNTrucks,
          })
        }
      }
    }

    return positions
  }, [])

  return { tickAndCollect }
}
