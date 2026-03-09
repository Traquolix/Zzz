import { useRef, useEffect, useCallback } from 'react'
import { useRealtime } from '@/hooks/useRealtime'
import { useFlowReset } from '@/hooks/useFlowReset'
import { parseDetections } from '@/lib/parseMessage'
import { channelToCoord, findFiber } from '../data'

interface LiveDot {
  lng: number
  lat: number
  speed: number
  ts: number
  fiberId: string
  direction: number
  channel: number
}

const DOT_TTL = 1000 // ms
const GEOJSON_THROTTLE_MS = 100 // rebuild GeoJSON at most 10Hz (not 60fps)

export function useDetections() {
  const { connected, subscribe } = useRealtime()
  const dotsRef = useRef(new Map<string, LiveDot>())
  const dirtyRef = useRef(false)
  const cachedGeoJSON = useRef<GeoJSON.FeatureCollection>({
    type: 'FeatureCollection',
    features: [],
  })
  const lastBuildRef = useRef(0)
  const lastDetectionTsRef = useRef(0)

  // Clear accumulated state on flow switch
  useFlowReset(() => {
    dotsRef.current.clear()
    dirtyRef.current = true
    lastDetectionTsRef.current = 0
    cachedGeoJSON.current = { type: 'FeatureCollection', features: [] }
  })

  useEffect(() => {
    // Pre-allocate a reusable key buffer to avoid per-detection string allocation
    const keyParts: string[] = ['', ':', '']

    const unsub = subscribe('detections', (data: unknown) => {
      const detections = parseDetections(data)
      if (detections.length === 0) return
      const now = Date.now()

      for (const d of detections) {
        if (d.timestamp > lastDetectionTsRef.current) {
          lastDetectionTsRef.current = d.timestamp
        }
        const fiber = findFiber(d.fiberId, d.direction)
        if (!fiber) continue
        const coord = channelToCoord(fiber, d.channel)
        if (!coord) continue

        keyParts[0] = fiber.id
        keyParts[2] = String(d.channel)
        const key = keyParts.join('')

        const existing = dotsRef.current.get(key)
        if (existing) {
          // Reuse existing object to avoid allocation
          existing.lng = coord[0]
          existing.lat = coord[1]
          existing.speed = d.speed
          existing.ts = now
        } else {
          dotsRef.current.set(key, {
            lng: coord[0],
            lat: coord[1],
            speed: d.speed,
            ts: now,
            fiberId: d.fiberId,
            direction: d.direction,
            channel: d.channel,
          })
        }
      }

      dirtyRef.current = true
    })

    return unsub
  }, [subscribe])

  const buildGeoJSON = useCallback((): GeoJSON.FeatureCollection => {
    const now = Date.now()

    // Throttle rebuilds — Mapbox can't render GeoJSON updates at 60fps anyway
    if (now - lastBuildRef.current < GEOJSON_THROTTLE_MS) {
      return cachedGeoJSON.current
    }

    let evicted = false

    // Evict expired dots
    for (const [key, dot] of dotsRef.current) {
      if (now - dot.ts > DOT_TTL) {
        dotsRef.current.delete(key)
        evicted = true
      }
    }

    if (!dirtyRef.current && !evicted) return cachedGeoJSON.current

    lastBuildRef.current = now

    const features: GeoJSON.Feature[] = []
    for (const dot of dotsRef.current.values()) {
      const age = now - dot.ts
      const opacity = 1.0 - age / DOT_TTL
      features.push({
        type: 'Feature',
        properties: { speed: dot.speed, opacity, fiberId: dot.fiberId, direction: dot.direction, channel: dot.channel },
        geometry: { type: 'Point', coordinates: [dot.lng, dot.lat] },
      })
    }

    cachedGeoJSON.current = { type: 'FeatureCollection', features }
    dirtyRef.current = false
    return cachedGeoJSON.current
  }, [])

  return { dotsRef, buildGeoJSON, connected, lastDetectionTsRef }
}
