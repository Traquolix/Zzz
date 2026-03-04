import { useRef, useEffect, useCallback } from 'react'
import { useRealtime } from '@/hooks/useRealtime'
import { parseDetections } from '@/lib/parseMessage'
import { channelToCoord } from '../data'

interface LiveDot {
    lng: number
    lat: number
    speed: number
    ts: number
    fiberLine: string
    channel: number
}

const DOT_TTL = 500 // ms
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

    useEffect(() => {
        const unsub = subscribe('detections', (data: unknown) => {
            const detections = parseDetections(data)
            const now = Date.now()

            for (const d of detections) {
                const coord = channelToCoord(d.fiberLine, d.channel)
                if (!coord) continue

                const key = `${d.fiberLine}:${d.channel}`
                dotsRef.current.set(key, {
                    lng: coord[0],
                    lat: coord[1],
                    speed: d.speed,
                    ts: now,
                    fiberLine: d.fiberLine,
                    channel: d.channel,
                })
            }

            if (detections.length > 0) dirtyRef.current = true
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
                properties: { speed: dot.speed, opacity, fiberLine: dot.fiberLine, channel: dot.channel },
                geometry: { type: 'Point', coordinates: [dot.lng, dot.lat] },
            })
        }

        cachedGeoJSON.current = { type: 'FeatureCollection', features }
        dirtyRef.current = false
        return cachedGeoJSON.current
    }, [])

    return { dotsRef, buildGeoJSON, connected }
}
